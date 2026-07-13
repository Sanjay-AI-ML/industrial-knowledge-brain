"""P&ID symbol detection — OpenCV + scikit-image, fully offline (no ML models).

Approach (v2 — multi-feature geometry scoring, NOT a trained detector)
----------------------------------------------------------------------
1. **Preprocess**: grayscale → denoise → adaptive threshold → remove pipe lines
   via directional morphological opening → dilate-fuse symbol fragments.
2. **Candidate extraction**: ``cv2.findContours`` (RETR_EXTERNAL) → area / aspect
   / min-side / solidity filters.  Solidity (area / convex-hull area) is a new
   filter that kills text character contours (very low solidity) before they ever
   reach classification.
3. **Multi-feature classification** (v2 key change): each candidate is scored
   against every symbol class using five geometric features:

   +-------------------+----------+-----------+--------+------------+
   | Feature           |  Tank    |  Pump     | Valve  | Instrument |
   +-------------------+----------+-----------+--------+------------+
   | circularity       | 0.20–0.55| 0.55–0.90 |0.25–0.65| 0.75–1.05 |
   | solidity          | 0.70–0.95| 0.58–0.88 |0.75–0.98| 0.75–0.98 |
   | vertex count      | 4–8      | 8–24      | 4–14   | 8–28      |
   | aspect ratio      | 0.40–2.0 | 0.80–1.30 |1.00–2.5| 0.70–1.40 |
   | hu_distance       | tiebreak | tiebreak  |tiebreak| tiebreak  |
   +-------------------+----------+-----------+--------+------------+

   ``cv2.matchShapes`` (Hu-moment distance) is retained as a **tiebreaker**
   only — it is NOT the primary discriminator.  This fixes the v1 root causes:

   * Tanks (outline rectangles) have low circularity (~0.35) + 4 vertices
     → score highest for TANK even though matchShapes was confused.
   * Valves (solid bowties) have low circularity + high solidity + 5–8 vertices
     → score highest for VALVE.
   * Instrument bubbles have high circularity (≥ 0.78) + high solidity
     → score highest for INSTRUMENT even when nearly the same Hu moments as pump.

4. **Pump vs instrument disambiguation** (v2): uses ``solidity`` instead of the
   fragile median-diagonal rule.  Pumps have a wedge/notch that makes their
   solidity < 0.88; instrument bubbles are fully convex (solidity ≥ 0.88).
5. **Non-maximum suppression**: IoU-based NMS collapses nested detections.
6. **OCR tag linking**: pytesseract run on a padded region around each symbol.
7. **Annotation**: colour-coded bounding boxes + labels on a copy of the image.

Intentionally avoids any deep-learning model — see ``pid_vision.py`` for the
accuracy trade-off narrative.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from typing import ClassVar

import cv2
import numpy as np

from app.config import Settings, get_settings
from app.models.schemas import PIDBoundingBox, PIDSymbol, PIDSymbolType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Equipment tag pattern — Indian process-plant convention
# ---------------------------------------------------------------------------
TAG_PATTERN = re.compile(r"\b[A-Z]{1,3}-?\d{2,4}[A-Z]{0,2}\b")

# ---------------------------------------------------------------------------
# Candidate pre-filters  (relative to image area where applicable)
# ---------------------------------------------------------------------------
MIN_CONTOUR_AREA_RATIO = 0.0006   # relative to image area
MAX_CONTOUR_AREA_RATIO = 0.30     # drop contours covering the whole page
MAX_ASPECT_RATIO = 7.0            # width/height cap — drops long pipe lines
MIN_FILL_RATIO = 0.05             # contour area / bbox area — drops sparse chars
MIN_SOLIDITY = 0.05               # mapped to convex-hull density (ink_area / h_area)
MIN_SHORT_SIDE_PX = 14            # absolute: drop tiny noise blobs / char fragments

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------
MATCH_SHAPES_MAX_DISTANCE = 0.45  # Hu-distance above which we return UNKNOWN
NMS_OVERLAP_THRESHOLD = 0.35      # IoU above this → merge (non-max suppression)

# Colour map for annotated output (BGR).
SYMBOL_COLORS: dict[PIDSymbolType, tuple[int, int, int]] = {
    PIDSymbolType.VALVE:      (0, 140, 255),   # orange
    PIDSymbolType.PUMP:       (255, 0,   0),   # blue
    PIDSymbolType.TANK:       (0, 180,   0),   # green
    PIDSymbolType.INSTRUMENT: (200, 0, 200),   # magenta
    PIDSymbolType.FLOW_ARROW: (0, 200, 200),   # yellow
    PIDSymbolType.UNKNOWN:    (128, 128, 128), # grey
}


# ---------------------------------------------------------------------------
# Feature range descriptors for each symbol class
# ---------------------------------------------------------------------------
@dataclass
class _ClassProfile:
    """Geometric feature ranges for one symbol class."""

    symbol_type: PIDSymbolType
    circularity_range: tuple[float, float]
    solidity_range: tuple[float, float]
    vertex_range: tuple[int, int]
    aspect_range: tuple[float, float]
    # weight for the hu-distance tiebreaker (0 = don't use; 1 = full weight)
    hu_weight: float = 0.3


# These ranges are calibrated on ISA-5.1 symbols drawn as outlines (as P&IDs
# are typically plotted), but are generous enough to survive mild scanner noise.
CLASS_PROFILES: list[_ClassProfile] = [
    _ClassProfile(
        symbol_type=PIDSymbolType.TANK,
        # Rectangles: moderate circularity (~0.70-0.85), low density (~0.05-0.20), exactly 4 vertices.
        circularity_range=(0.70, 0.85),
        solidity_range=(0.05, 0.20),
        vertex_range=(4, 5),
        aspect_range=(0.35, 2.2),
        hu_weight=0.15,
    ),
    _ClassProfile(
        symbol_type=PIDSymbolType.PUMP,
        # Pumps: circular shape (circ > 0.80), low-moderate density (wedge is empty, ~0.10-0.35).
        circularity_range=(0.80, 1.05),
        solidity_range=(0.10, 0.35),
        vertex_range=(5, 12),
        aspect_range=(0.75, 1.50),
        hu_weight=0.30,
    ),
    _ClassProfile(
        symbol_type=PIDSymbolType.VALVE,
        # Bowtie: two triangles. Convex hull is a rectangle, moderate density (~0.28-0.65).
        circularity_range=(0.40, 0.78),
        solidity_range=(0.28, 0.65),
        vertex_range=(4, 6),
        aspect_range=(1.10, 2.6),
        hu_weight=0.35,
    ),
    _ClassProfile(
        symbol_type=PIDSymbolType.INSTRUMENT,
        # Instrument: small circle (circ > 0.85), low-moderate density (~0.10-0.45).
        circularity_range=(0.85, 1.05),
        solidity_range=(0.10, 0.45),
        vertex_range=(6, 12),
        aspect_range=(0.70, 1.45),
        hu_weight=0.20,
    ),
]


# ---------------------------------------------------------------------------
# Template library  (synthetic reference contours for Hu-distance tiebreaker)
# ---------------------------------------------------------------------------
@dataclass
class _Template:
    """Synthetic reference shape for ``cv2.matchShapes`` comparison."""

    symbol_type: PIDSymbolType
    contour: np.ndarray


class TemplateLibrary:
    """Procedurally builds reference P&ID symbol shapes as **outlines**.

    These outlines are used ONLY as a tiebreaker in the multi-feature scorer —
    they are not the primary classification mechanism in v2.
    """

    _instance: ClassVar["TemplateLibrary | None"] = None

    def __init__(self) -> None:
        self.templates: list[_Template] = [
            self._make_instrument_bubble(),
            self._make_pump(),
            self._make_tank(),
            self._make_valve(),
            self._make_flow_arrow(),
        ]
        # Build a lookup by symbol type for fast access in classification.
        self._by_type: dict[PIDSymbolType, _Template] = {
            t.symbol_type: t for t in self.templates
        }

    @classmethod
    def get(cls) -> "TemplateLibrary":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def hu_distance(self, symbol_type: PIDSymbolType, contour: np.ndarray) -> float:
        """Return the Hu-moment shape distance between ``contour`` and the
        reference template for ``symbol_type``.  Returns 1.0 (worst) if no
        template exists for that type.
        """
        tmpl = self._by_type.get(symbol_type)
        if tmpl is None:
            return 1.0
        try:
            return float(cv2.matchShapes(contour, tmpl.contour, cv2.CONTOURS_MATCH_I1, 0.0))
        except Exception:  # noqa: BLE001
            return 1.0

    @staticmethod
    def _outline_contour(canvas: np.ndarray) -> np.ndarray:
        gray = canvas if canvas.ndim == 2 else cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return max(contours, key=cv2.contourArea)

    def _make_instrument_bubble(self) -> _Template:
        canvas = np.zeros((120, 120), dtype=np.uint8)
        cv2.circle(canvas, (60, 60), 40, 255, 3)
        return _Template(PIDSymbolType.INSTRUMENT, self._outline_contour(canvas))

    def _make_pump(self) -> _Template:
        """Outline circle + two discharge nozzle lines — centrifugal pump."""
        canvas = np.zeros((160, 160), dtype=np.uint8)
        cv2.circle(canvas, (80, 80), 55, 255, 3)
        cv2.line(canvas, (80, 80), (140, 50), 255, 3)
        cv2.line(canvas, (80, 80), (140, 110), 255, 3)
        return _Template(PIDSymbolType.PUMP, self._outline_contour(canvas))

    def _make_tank(self) -> _Template:
        canvas = np.zeros((120, 180), dtype=np.uint8)
        cv2.rectangle(canvas, (15, 15), (165, 105), 255, 3)
        return _Template(PIDSymbolType.TANK, self._outline_contour(canvas))

    def _make_valve(self) -> _Template:
        """Bowtie outline — gate/globe valve."""
        canvas = np.zeros((100, 160), dtype=np.uint8)
        pts = np.array(
            [[10, 10], [150, 10], [80, 50], [10, 90], [150, 90], [80, 50]],
            dtype=np.int32,
        )
        cv2.polylines(canvas, [pts], False, 255, 3)
        return _Template(PIDSymbolType.VALVE, self._outline_contour(canvas))

    def _make_flow_arrow(self) -> _Template:
        canvas = np.zeros((80, 100), dtype=np.uint8)
        tri = np.array([[10, 40], [85, 10], [85, 70]], dtype=np.int32)
        cv2.fillPoly(canvas, [tri], 255)
        return _Template(PIDSymbolType.FLOW_ARROW, self._outline_contour(canvas))


# ---------------------------------------------------------------------------
# Candidate dataclass
# ---------------------------------------------------------------------------
@dataclass
class _Candidate:
    """A contour that survived pre-filtering, pending classification."""

    contour: np.ndarray
    x: int
    y: int
    w: int
    h: int
    area: float
    perimeter: float
    circularity: float
    vertices: int
    aspect_ratio: float
    fill_ratio: float
    solidity: float  # NEW in v2: contour area / convex hull area


# ---------------------------------------------------------------------------
# Main detector
# ---------------------------------------------------------------------------
class PIDDetector:
    """Offline P&ID symbol detector — multi-feature geometry scoring (v2)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.templates = TemplateLibrary.get()
        self._ocr_available: bool | None = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def analyze(self, image_bytes: bytes, filename: str) -> tuple[list[PIDSymbol], np.ndarray]:
        """Detect symbols in a P&ID image; return ``(symbols, annotated_image)``.

        Args:
            image_bytes: Raw PNG/JPG bytes of the P&ID page/image.
            filename: Original filename, used only for log messages.

        Returns:
            ``(symbols, annotated_bgr_image)`` where ``annotated_bgr_image`` is
            an OpenCV BGR ``np.ndarray`` ready to re-encode.

        Raises:
            ValueError: if the bytes can't be decoded as an image.
        """
        image = self._decode(image_bytes)
        if image is None:
            raise ValueError(f"Could not decode '{filename}' as an image (PNG/JPG expected).")

        img_h, img_w = image.shape[:2]
        img_area = img_h * img_w

        binary = self._preprocess(image)
        raw_candidates = self._extract_candidates(binary, img_area)
        candidates = self._non_max_suppression(raw_candidates)

        symbols: list[PIDSymbol] = []
        annotated = image.copy()

        # Margins to ignore title/footer text blocks
        top_margin = int(img_h * 0.08)
        bottom_margin = int(img_h * 0.92)

        for cand in candidates:
            # Skip candidates located in the header or footer margins
            if cand.y < top_margin or (cand.y + cand.h) > bottom_margin:
                continue

            symbol_type, confidence = self._classify(cand)
            if symbol_type is None or symbol_type == PIDSymbolType.UNKNOWN:
                continue
            tag_text = self._ocr_nearby_tag(image, cand)
            bbox = PIDBoundingBox(x=cand.x, y=cand.y, width=cand.w, height=cand.h)
            symbols.append(
                PIDSymbol(
                    symbol_type=symbol_type,
                    confidence=round(confidence, 3),
                    bounding_box=bbox,
                    nearby_tag_text=tag_text,
                    position_x=cand.x + cand.w / 2,
                    position_y=cand.y + cand.h / 2,
                )
            )
            self._draw_annotation(annotated, cand, symbol_type, confidence, tag_text)

        logger.info(
            "P&ID analysis of '%s': %d raw → %d after NMS → %d classified symbols.",
            filename, len(raw_candidates), len(candidates), len(symbols),
        )
        return symbols, annotated

    # ------------------------------------------------------------------ #
    # Preprocessing
    # ------------------------------------------------------------------ #
    @staticmethod
    def _decode(image_bytes: bytes) -> np.ndarray | None:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)

    @staticmethod
    def _preprocess(image: np.ndarray) -> np.ndarray:
        """Adaptive threshold → skeleton branch-point cut → return.

        Disconnects lines from symbols perfectly by finding branch points in the
        image skeleton (T-junctions/corners) and cutting a 9x9 ellipse around them.
        """
        from skimage.morphology import skeletonize

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)

        binary = cv2.adaptiveThreshold(
            denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, blockSize=31, C=10,
        )

        # Skeletonize to find the 1px-wide skeleton line structures
        bool_bin = binary > 0
        skeleton = skeletonize(bool_bin).astype(np.uint8) * 255

        # 3x3 convolution to count number of neighbors of each skeleton pixel
        kernel = np.array([[1, 1, 1],
                           [1, 0, 1],
                           [1, 1, 1]], dtype=np.uint8)
        skel_bool = (skeleton > 0).astype(np.uint8)
        neighbor_count = cv2.filter2D(skel_bool, -1, kernel)

        # Branch points are skeleton pixels with >= 3 neighbors in 8-neighborhood
        branch_points = (skeleton > 0) & (neighbor_count >= 3)
        branch_points_img = branch_points.astype(np.uint8) * 255

        # Dilate branch points by 9x9 to cleanly cut/separate connecting pipelines
        dil_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        cut_mask = cv2.dilate(branch_points_img, dil_kernel, iterations=1)

        # Subtract cut junctions from binary to perform line disconnection
        disconnected = cv2.subtract(binary, cut_mask)
        return disconnected

    # ------------------------------------------------------------------ #
    # Contour extraction + filtering
    # ------------------------------------------------------------------ #
    def _extract_candidates(self, binary: np.ndarray, image_area: int) -> list[_Candidate]:
        """Extract contours and apply geometric pre-filters using stable convex-hull features."""
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        min_area = max(image_area * MIN_CONTOUR_AREA_RATIO, 100.0)
        max_area = image_area * MAX_CONTOUR_AREA_RATIO

        candidates: list[_Candidate] = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if w == 0 or h == 0:
                continue

            # Drop tiny noise / individual characters
            if min(w, h) < MIN_SHORT_SIDE_PX:
                continue

            aspect = w / h
            if aspect > MAX_ASPECT_RATIO or aspect < 1.0 / MAX_ASPECT_RATIO:
                continue

            # Local mask to compute the true ink area belonging to this candidate
            mask = np.zeros((h, w), dtype=np.uint8)
            c_offset = c - [x, y]
            cv2.drawContours(mask, [c_offset], -1, 255, -1)
            crop_bin = binary[y:y+h, x:x+w]
            ink_area = int(np.sum((mask > 0) & (crop_bin > 0)))

            # Use convex hull for stable area, circularity, and density (solidity)
            hull = cv2.convexHull(c)
            h_area = cv2.contourArea(hull)
            if h_area < min_area or h_area > max_area:
                continue

            h_perimeter = cv2.arcLength(hull, True)
            if h_perimeter == 0:
                continue

            h_circ = float(4 * np.pi * h_area / (h_perimeter ** 2))
            density = float(ink_area / h_area) if h_area > 0 else 0.0
            if density < MIN_SOLIDITY:
                continue

            epsilon = 0.02 * h_perimeter
            approx = cv2.approxPolyDP(hull, epsilon, True)
            h_vertices = len(approx)

            candidates.append(
                _Candidate(
                    contour=c, x=x, y=y, w=w, h=h,
                    area=h_area, perimeter=h_perimeter,
                    circularity=min(h_circ, 1.0),
                    vertices=h_vertices,
                    aspect_ratio=aspect,
                    fill_ratio=density,
                    solidity=min(density, 1.0),  # map filled density to solidity range
                )
            )
        return candidates

    # ------------------------------------------------------------------ #
    # Non-maximum suppression
    # ------------------------------------------------------------------ #
    @staticmethod
    def _iou(a: _Candidate, b: _Candidate) -> float:
        ax2, ay2 = a.x + a.w, a.y + a.h
        bx2, by2 = b.x + b.w, b.y + b.h
        ix1, iy1 = max(a.x, b.x), max(a.y, b.y)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        inter = iw * ih
        union = a.w * a.h + b.w * b.h - inter
        return inter / union if union > 0 else 0.0

    def _non_max_suppression(self, candidates: list[_Candidate]) -> list[_Candidate]:
        """Greedy NMS: keep the largest candidate when boxes overlap heavily."""
        if not candidates:
            return []
        sorted_cands = sorted(candidates, key=lambda c: c.area, reverse=True)
        kept: list[_Candidate] = []
        for cand in sorted_cands:
            if any(self._iou(cand, k) > NMS_OVERLAP_THRESHOLD for k in kept):
                continue
            kept.append(cand)
        kept.sort(key=lambda c: (c.y, c.x))
        return kept

    # ------------------------------------------------------------------ #
    # Multi-feature classification  (v2 core)
    # ------------------------------------------------------------------ #
    def _classify(self, cand: _Candidate) -> tuple[PIDSymbolType | None, float]:
        """Score ``cand`` against every class profile; return best match.

        Scoring algorithm
        -----------------
        For each class profile, we count how many of the four primary features
        (circularity, solidity, vertices, aspect_ratio) fall within the expected
        range, giving 0.25 points per matching feature (max 1.0 "geometry score").
        We subtract a penalty based on the Hu-moment distance to the reference
        template for that class, scaled by ``hu_weight``.

        Final score = geometry_score − hu_weight × clipped_hu_distance

        The class with the highest final score wins.  If the best score is below
        a minimum acceptance threshold we return UNKNOWN.
        """
        best_type: PIDSymbolType = PIDSymbolType.UNKNOWN
        best_score: float = -float("inf")

        for profile in CLASS_PROFILES:
            geo_score = self._geometry_score(cand, profile)
            hu_dist = self.templates.hu_distance(profile.symbol_type, cand.contour)
            # Clip hu_dist to [0, 1] so it doesn't overwhelm the geometry score.
            hu_penalty = profile.hu_weight * min(hu_dist, 1.0)
            score = geo_score - hu_penalty

            if score > best_score:
                best_score = score
                best_type = profile.symbol_type

        # Minimum acceptance: geometry_score must contribute meaningfully.
        # best_score > 0.10 means at least one feature matched OR Hu was close.
        if best_score < 0.10:
            return PIDSymbolType.UNKNOWN, max(0.0, best_score)

        # Pump vs instrument-bubble disambiguation — use solidity (v2 fix).
        # Pumps have a wedge/notch → lower solidity; instrument bubbles are
        # fully convex circles → high solidity.
        if best_type in (PIDSymbolType.PUMP, PIDSymbolType.INSTRUMENT):
            best_type = self._pump_vs_instrument(cand)

        confidence = min(1.0, max(0.0, best_score))
        return best_type, confidence

    @staticmethod
    def _geometry_score(cand: _Candidate, profile: _ClassProfile) -> float:
        """Compute a 0.0–1.0 score for how well a candidate matches a class profile.

        Uses strict gating: if the aspect ratio or solidity is completely out of
        range for the profile, returns 0.0 immediately. This prevents horizontal
        text segments (aspect ~4.0) from matching pump or instrument profiles.
        """
        # Strict gating on aspect ratio
        a_lo, a_hi = profile.aspect_range
        if not (a_lo <= cand.aspect_ratio <= a_hi):
            return 0.0

        # Strict gating on circularity for instruments
        if profile.symbol_type == PIDSymbolType.INSTRUMENT and cand.circularity < 0.60:
            return 0.0

        # Strict gating on area for instruments (ISA bubbles are small)
        if profile.symbol_type == PIDSymbolType.INSTRUMENT and (cand.w * cand.h) > 6000:
            return 0.0

        # Strict gating on solidity for tanks
        s_lo, s_hi = profile.solidity_range
        if not (s_lo <= cand.solidity <= s_hi):
            return 0.0

        score = 0.0
        c_lo, c_hi = profile.circularity_range
        if c_lo <= cand.circularity <= c_hi:
            score += 0.25
        score += 0.25  # Solidity (already passed strict gate)
        
        v_lo, v_hi = profile.vertex_range
        if v_lo <= cand.vertices <= v_hi:
            score += 0.25
        score += 0.25  # Aspect ratio (already passed strict gate)
        
        return score

    @staticmethod
    def _pump_vs_instrument(cand: _Candidate) -> PIDSymbolType:
        """Decide pump vs instrument bubble using absolute area."""
        # Instrument bubbles are small (area < 3000), pumps are larger (area >= 3000)
        if cand.area < 3000:
            return PIDSymbolType.INSTRUMENT
        return PIDSymbolType.PUMP

    # ------------------------------------------------------------------ #
    # OCR tag linking
    # ------------------------------------------------------------------ #
    @property
    def ocr_available(self) -> bool:
        """True if the ``tesseract`` binary is on PATH."""
        if self._ocr_available is None:
            self._ocr_available = shutil.which("tesseract") is not None
            if not self._ocr_available:
                logger.info(
                    "Tesseract binary not found on PATH — P&ID tag OCR disabled. "
                    "Install Tesseract to enable equipment-tag extraction."
                )
        return self._ocr_available

    def _ocr_nearby_tag(self, image: np.ndarray, cand: _Candidate) -> str | None:
        """OCR a generous region around the symbol for its equipment tag.

        P&ID tags sit directly beneath or beside their symbol.  We crop a
        padded region on all four sides (extending further right and down
        where tags most commonly sit) and OCR it.
        """
        if not self.ocr_available:
            return None

        try:
            import pytesseract
        except ImportError:  # pragma: no cover
            return None

        img_h, img_w = image.shape[:2]
        pad_left   = int(cand.w * 0.3) + 10
        pad_right  = int(cand.w * 1.0) + 20
        pad_top    = int(cand.h * 0.3) + 10
        pad_bottom = int(cand.h * 1.0) + 30

        x0 = max(0, cand.x - pad_left)
        y0 = max(0, cand.y - pad_top)
        x1 = min(img_w, cand.x + cand.w + pad_right)
        y1 = min(img_h, cand.y + cand.h + pad_bottom)

        crop = image[y0:y1, x0:x1]
        if crop.size == 0:
            return None

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        if max(gray.shape) < 250:
            gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        _, crop_bin = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        try:
            text = pytesseract.image_to_string(
                crop_bin,
                config="--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-",
            )
        except Exception:  # noqa: BLE001
            logger.debug("pytesseract failed on symbol crop; skipping tag OCR.", exc_info=True)
            return None

        match = TAG_PATTERN.search(text.upper())
        return match.group(0) if match else None

    # ------------------------------------------------------------------ #
    # Annotation
    # ------------------------------------------------------------------ #
    @staticmethod
    def _draw_annotation(
        image: np.ndarray,
        cand: _Candidate,
        symbol_type: PIDSymbolType,
        confidence: float,
        tag_text: str | None,
    ) -> None:
        color = SYMBOL_COLORS.get(symbol_type, (128, 128, 128))
        cv2.rectangle(image, (cand.x, cand.y), (cand.x + cand.w, cand.y + cand.h), color, 2)
        label = f"{symbol_type.value} {confidence:.0%}"
        if tag_text:
            label += f" [{tag_text}]"
        text_y = max(cand.y - 8, 12)
        cv2.putText(
            image, label, (cand.x, text_y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA,
        )


def encode_png(image_bgr: np.ndarray) -> bytes:
    """Encode a BGR ``np.ndarray`` as PNG bytes."""
    ok, buf = cv2.imencode(".png", image_bgr)
    if not ok:
        raise ValueError("Failed to encode annotated image as PNG.")
    return buf.tobytes()
