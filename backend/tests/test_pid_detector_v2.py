"""Quick offline test of the v2 PID detector on both sample images.

Run from the backend/ directory:
    python tests/test_pid_detector_v2.py

Does NOT need the FastAPI server running — calls PIDDetector directly.
"""

import sys
from pathlib import Path

# Ensure the app package is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
from app.core.pid_detector import PIDDetector, encode_png
from app.models.schemas import PIDSymbolType


SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_documents"


def test_pid(image_path: Path, expected_types: list[str]) -> bool:
    """Run detection, print summary, return True if no UNKNOWN detections."""
    print(f"\n{'='*60}")
    print(f"Image: {image_path.name}")
    print(f"{'='*60}")

    image_bytes = image_path.read_bytes()
    detector = PIDDetector()
    symbols, annotated = detector.analyze(image_bytes, image_path.name)

    # Save annotated output for visual inspection.
    out_path = SAMPLE_DIR / f"_v2_annotated_{image_path.stem}.png"
    out_path.write_bytes(encode_png(annotated))
    print(f"Annotated output saved: {out_path}")

    # Print per-symbol results.
    print(f"\nDetected {len(symbols)} symbols:")
    counts: dict[str, int] = {}
    unknown_count = 0
    for s in symbols:
        tag = s.nearby_tag_text or "(no tag)"
        print(f"  {s.symbol_type.value:22s}  conf={s.confidence:.2f}  tag={tag}")
        counts[s.symbol_type.value] = counts.get(s.symbol_type.value, 0) + 1
        if s.symbol_type == PIDSymbolType.UNKNOWN:
            unknown_count += 1

    print(f"\nSymbol counts: {counts}")
    print(f"UNKNOWN detections: {unknown_count}  (target: 0)")

    ok = unknown_count == 0
    print(f"\n{'PASS' if ok else 'WARN'}: {'No false detections!' if ok else f'{unknown_count} UNKNOWN shape(s) — check annotated image'}")
    return ok


def main() -> None:
    all_pass = True

    # 1. sample_pid.png — the richer test fixture (tanks + pumps + valves + instruments)
    sample_pid = SAMPLE_DIR / "sample_pid.png"
    if sample_pid.exists():
        ok = test_pid(sample_pid, expected_types=["tank", "pump", "valve", "instrument_bubble"])
        all_pass = all_pass and ok
    else:
        print(f"SKIP: {sample_pid} not found")

    # 2. sample_pid_synthetic.png — simple synthetic P&ID
    synthetic_pid = SAMPLE_DIR / "sample_pid_synthetic.png"
    if synthetic_pid.exists():
        ok = test_pid(synthetic_pid, expected_types=["tank", "pump", "valve", "instrument_bubble"])
        all_pass = all_pass and ok
    else:
        print(f"SKIP: {synthetic_pid} not found (run generate_sample_pid.py first)")

    print(f"\n{'='*60}")
    print(f"Overall: {'ALL PASS' if all_pass else 'SOME WARNINGS — review annotated images'}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
