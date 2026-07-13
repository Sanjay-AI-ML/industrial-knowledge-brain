# Master prompt — Industrial Knowledge Brain, next iteration

Paste this into a new chat (with the Filesystem connector pointed at
`industrial-knowledge-brain`) whenever you want to push the project further.
Edit the "Focus area" section each time to pick what to work on.

---

I'm continuing work on **Industrial Knowledge Brain**, a FastAPI + React
platform for Indian industrial plants (document ingestion, RAG copilot, P&ID
computer vision, maintenance RCA, compliance gap tracking). All 6 phases are
built and working. Tech stack: FastAPI, Gemini 2.5 Flash, ChromaDB, Neo4j,
OpenCV/scikit-image (no YOLO), faster-whisper + Bhashini, React/Vite/Tailwind.

Read `README.md`, `docs/ARCHITECTURE.md`, and `docs/API.md` first to load
current state before changing anything. Follow the conventions in
`CONTRIBUTING.md` (docstrings, graceful degradation, dark-mode-safe Tailwind
classes, updating both `.env.example` files + `docker-compose.yml` for new
env vars, documenting new endpoints in `docs/API.md`).

## Focus area for this session
<!-- Replace this line with what you want done, e.g.: -->
<!-- "Add a pytest test suite for the backend core/ modules" -->
<!-- "Add JWT auth (auth.py is currently a stub) and protect /api/ingest" -->
<!-- "Add a real Dashboard chart of ingestion volume over time" -->
<!-- "Swap PIDDetector for a fine-tuned YOLOv8 model, same interface" -->

## Ground rules
- Read the relevant existing files before editing — don't guess at schemas,
  route signatures, or component props.
- Keep the "graceful degradation" pattern: a down dependency (Neo4j, Gemini,
  Bhashini) should degrade a feature, not crash the whole app.
- Any new structural (gray/white/slate) Tailwind class in a frontend
  component needs a matching override added to the dark-mode block in
  `frontend/src/index.css`, or it'll look broken in dark mode. Colored accent
  badges (bg-*-50 chips) don't need this.
- Any new required env var needs to land in the root `.env.example` (and
  `docker-compose.yml`'s `environment:` block if container-specific).
- Update `docs/API.md` for any new/changed endpoint.
- Don't commit secrets; `.env` stays gitignored.

## Standing candidate improvements (pick from here if no specific ask)
1. **Automated tests** — no pytest suite exists yet; start with
   `pid_detector.py` (pure function, easy to unit test) and the schema
   validation layer.
2. **Auth** — `auth.py` is a stub; wire up real JWT login + a
   `Depends(get_current_user)` guard on ingestion/compliance endpoints.
3. **CI** — a GitHub Actions workflow to lint (ruff/eslint) + run tests on
   PRs would raise this from "hackathon project" to "production repo."
4. **Streaming responses** — `/api/query` and `/api/voice/query` currently
   return once fully generated; consider SSE/streaming for the Copilot chat
   for a snappier UX.
5. **Dashboard depth** — the new Dashboard page currently shows health +
   nav cards; could add real ingestion-volume/query-volume charts (recharts
   is already an available library convention in this codebase's frontend
   design guidance).
6. **Rate limiting / input size guards** — ingestion and voice endpoints cap
   file size already; consider a basic rate limiter if this is ever exposed
   beyond localhost.
7. **P&ID detector accuracy** — see `docs/PID_VISION_GUIDE.md` "upgrade path"
   section for the YOLO/Detectron2 swap-in plan, if real-world accuracy
   becomes the bottleneck.
