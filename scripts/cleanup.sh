#!/usr/bin/env bash
# One-time cleanup of debug artifacts and duplicate files accumulated during
# development. Safe to delete all of these — none are referenced by the
# application; they were left over from interactive CV debugging.
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Removing backend debug images..."
rm -f backend/_debug_filled.png \
      backend/_debug_filled_contours.png \
      backend/_debug_fused_contours.png \
      backend/_debug_tank_crop.png \
      backend/_debug_valve_crop.png \
      backend/_debug_valve_fused.png \
      backend/sample_pid_annotated_DEBUG.png

echo "Removing sample_documents debug/duplicate artifacts..."
rm -f backend/data/sample_documents/_debug_binary.png \
      backend/data/sample_documents/_debug_contours.png \
      backend/data/sample_documents/_debug_lines.png \
      backend/data/sample_documents/_debug_symbols_contours.png \
      backend/data/sample_documents/_debug_symbols_only.png \
      backend/data/sample_documents/_v2_annotated_sample_pid.png \
      backend/data/sample_documents/_v2_annotated_sample_pid_synthetic.png \
      backend/data/sample_documents/sample_pid_annotated_DEBUG.png \
      backend/data/sample_documents/sample_pid_synthetic.png \
      backend/data/sample_documents/generate_sample_pid.py

echo
echo "Done. Kept:"
echo "  - backend/scripts/generate_sample_pid.py   (canonical generator)"
echo "  - backend/data/sample_documents/sample_pid.png  (canonical sample image)"
echo "  - backend/data/sample_documents/*.txt / *.pdf   (ingestion sample docs)"
