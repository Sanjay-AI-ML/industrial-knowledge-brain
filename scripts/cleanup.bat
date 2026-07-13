@echo off
rem One-time cleanup of debug artifacts and duplicate files accumulated
rem during development. Safe to delete all of these — none are referenced
rem by the application; they were left over from interactive CV debugging.
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"

echo Removing backend debug images...
del /q "backend\_debug_filled.png" 2>nul
del /q "backend\_debug_filled_contours.png" 2>nul
del /q "backend\_debug_fused_contours.png" 2>nul
del /q "backend\_debug_tank_crop.png" 2>nul
del /q "backend\_debug_valve_crop.png" 2>nul
del /q "backend\_debug_valve_fused.png" 2>nul
del /q "backend\sample_pid_annotated_DEBUG.png" 2>nul

echo Removing sample_documents debug/duplicate artifacts...
del /q "backend\data\sample_documents\_debug_binary.png" 2>nul
del /q "backend\data\sample_documents\_debug_contours.png" 2>nul
del /q "backend\data\sample_documents\_debug_lines.png" 2>nul
del /q "backend\data\sample_documents\_debug_symbols_contours.png" 2>nul
del /q "backend\data\sample_documents\_debug_symbols_only.png" 2>nul
del /q "backend\data\sample_documents\_v2_annotated_sample_pid.png" 2>nul
del /q "backend\data\sample_documents\_v2_annotated_sample_pid_synthetic.png" 2>nul
del /q "backend\data\sample_documents\sample_pid_annotated_DEBUG.png" 2>nul
del /q "backend\data\sample_documents\sample_pid_synthetic.png" 2>nul
del /q "backend\data\sample_documents\generate_sample_pid.py" 2>nul

echo.
echo Done. Kept:
echo   - backend\scripts\generate_sample_pid.py   (canonical generator)
echo   - backend\data\sample_documents\sample_pid.png  (canonical sample image)
echo   - backend\data\sample_documents\*.txt / *.pdf   (ingestion sample docs)
echo.
pause
