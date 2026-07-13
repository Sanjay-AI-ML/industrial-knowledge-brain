# Troubleshooting

## Windows: `start.bat` fails with `'Setup' is not recognized` or `... was unexpected at this time`

Fixed in the current version of `start.bat` — this was caused by an unescaped `&` in an `echo` line (batch treats `&` as a command separator) combined with fragile nested-parentheses `if` blocks. If you're on an old copy of the script, re-pull/re-copy the latest `start.bat`.

## Dashboard shows "Can't reach the backend at localhost:8000"

This means the frontend is up but the backend process isn't (or crashed). To debug:

1. Open a terminal and run the backend directly, so you can see any error instead of a window closing silently:
   ```bat
   cd backend
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
2. If it prints `Uvicorn running on http://0.0.0.0:8000` and stays open — success. Leave that window running, then reload the frontend.
3. If it prints a traceback, the error message will tell you what's missing (see below for common ones).
4. Confirm directly in a browser: http://localhost:8000/health should return JSON like `{"status":"healthy", ...}`. If that fails, the backend genuinely isn't running — a CORS/frontend issue would still let `/health` load fine.

## Docker Compose: `GEMINI_API_KEY` empty inside the container

The backend container reads config from the **project-root `.env`** (same file used by local `uvicorn` — see `backend/app/config.py`). Make sure you've run `cp .env.example .env` in the project root and filled in `GEMINI_API_KEY` there.

## `ModuleNotFoundError` / import errors on backend startup

Dependencies aren't installed (or you're in the wrong Python environment).
```bat
cd backend
python -m pip install -r requirements.txt
```
If you use a virtualenv, make sure it's activated before running `uvicorn`.

## OCR / PDF parsing silently skips scanned pages

`pytesseract` and `pdf2image` are Python wrappers — they need the underlying **Tesseract OCR** and **Poppler** binaries installed separately and on your `PATH`. Without them, ingestion still works for text-based PDFs; scanned/image-only pages are just skipped rather than erroring (`ocr_fallback_enabled` degrades gracefully by design). To enable OCR on Windows:

- Tesseract: https://github.com/UB-Mannheim/tesseract/wiki (installer adds it to PATH)
- Poppler: https://github.com/oschwartz10612/poppler-windows/releases (add the `bin/` folder to PATH manually)

Restart your terminal after installing either so the updated `PATH` takes effect.

## Neo4j unreachable

`GET /health` will show `"neo4j": {"reachable": false}`. This does **not** crash the app — ingestion/RCA/compliance just skip the graph-linking step and report it in their responses.

- **Docker path**: the bundled `neo4j` container should come up automatically; check `docker compose logs neo4j`.
- **Local path**: confirm `NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` in the root `.env` match a running instance (AuraDB or local Neo4j Desktop), and that the AuraDB instance isn't paused (free tier instances auto-pause after inactivity).

## Port already in use

If `8000` or `5173` is already taken by something else, either stop that process or change the port:
```bat
uvicorn app.main:app --host 0.0.0.0 --port 8001
```
(and update `API_BASE` in the frontend `src/pages/*.jsx` files / set `VITE_API_BASE` accordingly if you do this long-term).

## Frontend shows a blank/broken page after pulling new changes

Usually a missing dependency after a `package.json` update (e.g. `lucide-react`).
```bat
cd frontend
npm install
npm run dev
```

## Still stuck?

Open the relevant service's terminal window and copy the **full** error text — most issues here are one specific line in a traceback, not the whole log.
