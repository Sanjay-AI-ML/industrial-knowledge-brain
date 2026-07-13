"""Generate a small synthetic sample P&ID image for testing pid_detector.py.

This draws a handful of canonical P&ID shapes (tank/rectangle, valve/bowtie,
pump/notched-circle, instrument bubble/small circle, flow arrow/triangle)
plus nearby tag text, using only OpenCV — no external assets, so it always
matches what ``PIDDetector`` was built to recognize.

This is a *synthetic* test fixture, not a realistic scanned P&ID. It exists
so you have something to run through /api/pid/analyze immediately, without
needing a real scanned drawing on hand.

Usage
-----
    cd backend
    python scripts/generate_sample_pid.py

Output
------
    backend/data/sample_documents/sample_pid.png
"""

from __future__ import annotations

import os

import cv2
import numpy as np

OUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "sample_documents",
    "sample_pid.png",
)

WIDTH, HEIGHT = 1000, 700
BLACK = (30, 30, 30)
WHITE = (255, 255, 255)


def draw_tank(canvas: np.ndarray, cx: int, cy: int, tag: str) -> None:
    """Rectangle vessel, e.g. TK-101."""
    x0, y0, x1, y1 = cx - 70, cy - 90, cx + 70, cy + 90
    cv2.rectangle(canvas, (x0, y0), (x1, y1), BLACK, 3)
    cv2.putText(canvas, tag, (x0 - 5, y1 + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, BLACK, 2, cv2.LINE_AA)


def draw_valve(canvas: np.ndarray, cx: int, cy: int, tag: str) -> None:
    """Bowtie (two opposing triangles), e.g. V-203."""
    left = np.array([[cx - 45, cy - 25], [cx, cy], [cx - 45, cy + 25]], dtype=np.int32)
    right = np.array([[cx + 45, cy - 25], [cx, cy], [cx + 45, cy + 25]], dtype=np.int32)
    cv2.fillPoly(canvas, [left, right], BLACK)
    cv2.putText(canvas, tag, (cx - 30, cy + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.6, BLACK, 2, cv2.LINE_AA)


def draw_pump(canvas: np.ndarray, cx: int, cy: int, tag: str) -> None:
    """Circle with a wedge notch (larger than an instrument bubble), e.g. P-101A."""
    cv2.circle(canvas, (cx, cy), 42, BLACK, 3)
    wedge = np.array([[cx, cy], [cx + 60, cy - 22], [cx + 60, cy + 22]], dtype=np.int32)
    cv2.fillPoly(canvas, [wedge], WHITE)
    cv2.polylines(canvas, [wedge], True, BLACK, 2)
    cv2.putText(canvas, tag, (cx - 35, cy + 65), cv2.FONT_HERSHEY_SIMPLEX, 0.65, BLACK, 2, cv2.LINE_AA)


def draw_instrument(canvas: np.ndarray, cx: int, cy: int, tag: str) -> None:
    """Small circle — ISA instrument bubble, e.g. PI-101."""
    cv2.circle(canvas, (cx, cy), 22, BLACK, 3)
    cv2.putText(canvas, tag, (cx - 26, cy + 42), cv2.FONT_HERSHEY_SIMPLEX, 0.5, BLACK, 2, cv2.LINE_AA)


def draw_flow_arrow(canvas: np.ndarray, x: int, y: int) -> None:
    """Small isosceles triangle marking flow direction on a line."""
    tri = np.array([[x, y - 12], [x + 26, y], [x, y + 12]], dtype=np.int32)
    cv2.fillPoly(canvas, [tri], BLACK)


def draw_line(canvas: np.ndarray, p0: tuple[int, int], p1: tuple[int, int]) -> None:
    cv2.line(canvas, p0, p1, BLACK, 2)


def main() -> None:
    canvas = np.full((HEIGHT, WIDTH, 3), 255, dtype=np.uint8)

    cv2.putText(
        canvas, "SAMPLE P&ID - SYNTHETIC TEST FIXTURE", (280, 40),
        cv2.FONT_HERSHEY_SIMPLEX, 0.8, BLACK, 2, cv2.LINE_AA,
    )

    # Feed tank -> pump -> valve -> reactor tank, with an instrument bubble
    # and flow arrows on the connecting lines.
    draw_tank(canvas, 150, 300, "TK-101")
    draw_line(canvas, (220, 300), (330, 300))
    draw_flow_arrow(canvas, 265, 300)

    draw_pump(canvas, 380, 300, "P-101A")
    draw_line(canvas, (440, 300), (540, 300))
    draw_flow_arrow(canvas, 480, 300)

    draw_valve(canvas, 580, 300, "V-203")
    draw_line(canvas, (630, 300), (740, 300))
    draw_flow_arrow(canvas, 675, 300)

    draw_tank(canvas, 830, 300, "TK-450")

    draw_instrument(canvas, 380, 150, "PI-101")
    draw_line(canvas, (380, 172), (380, 258))

    draw_instrument(canvas, 830, 150, "TI-450")
    draw_line(canvas, (830, 172), (830, 210))

    # A second, smaller pump + valve pair lower on the sheet for more
    # detections to demo with.
    draw_pump(canvas, 380, 520, "P-101B")
    draw_valve(canvas, 580, 520, "V-204")
    draw_line(canvas, (440, 520), (540, 520))
    draw_flow_arrow(canvas, 480, 520)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    cv2.imwrite(OUT_PATH, canvas)
    print(f"Wrote sample P&ID to: {OUT_PATH}")


if __name__ == "__main__":
    main()
