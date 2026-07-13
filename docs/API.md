# API Reference

Base URL (local): `http://localhost:8000`

Interactive Swagger UI (auto-generated from the same schemas): **http://localhost:8000/docs**
ReDoc: **http://localhost:8000/redoc**

This file is a quick-scan reference; the Swagger UI is always the source of truth for exact request/response shapes since it's generated directly from the Pydantic models.

---

## Meta

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness + connectivity probe for ChromaDB and Neo4j. Always returns 200; failures are reported in the payload, not as HTTP errors. |

---

## Ingestion

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/ingest` | Upload a PDF. Runs the full pipeline: parse (pdfplumber/OCR) → entity extraction (Gemini) → knowledge graph write (Neo4j) → vector embed (ChromaDB). Returns structured status per stage — a failure in one stage (e.g. Neo4j down) doesn't fail the others. |

**Request:** `multipart/form-data`, field `file` (PDF, ≤50MB).

---

## Knowledge Copilot (RAG)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/query/health` | Liveness probe. |
| POST | `/api/query` | Ask a natural-language question. Hybrid retrieval: ChromaDB vector search + Neo4j graph enrichment, answered by Gemini with citations. |

**Request body:**
```json
{ "question": "What is the vibration trip limit for P-101A?", "role": "engineer", "session_id": null }
```
`role` is one of `technician` / `engineer` / `auditor` — changes answer style, not retrieval. Omit `session_id` to start a new conversation; pass the one returned in the response to continue it.

---

## P&ID Vision

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/pid/health` | Liveness probe. |
| POST | `/api/pid/analyze` | Upload a P&ID image (PNG/JPG/BMP/TIFF — convert PDFs to an image first). Detects valves, pumps, tanks, instrument bubbles, and flow arrows via OpenCV contour + Hu-moment shape matching (no ML model). Returns detected symbols, an annotated image (base64 PNG), and optionally links OCR'd equipment tags into Neo4j. |

**Query param:** `link_to_graph` (bool, default `true`).
**Request:** `multipart/form-data`, field `file`.

See [`PID_VISION_GUIDE.md`](./PID_VISION_GUIDE.md) for detection accuracy notes and a full manual test checklist.

---

## Maintenance & RCA

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/maintenance/health` | Liveness probe. |
| POST | `/api/maintenance/rca` | Runs a LangGraph 5-Whys workflow: resolves an equipment tag from a free-text query, pulls Neo4j history + ChromaDB OEM guides, and has Gemini compile a fishbone-style root cause report. |
| GET | `/api/maintenance/risk-score/{equipment_tag}` | Heuristic 0–100 risk score for an asset, derived from the volume/type of linked graph history. |

**RCA request body:**
```json
{ "query": "vibration and oil leakage observed on P-101A during routine shift rounds" }
```

---

## Compliance

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/compliance/health` | Liveness probe; also reports how many reference regulations are loaded. |
| POST | `/api/compliance/gap-analysis` | Cross-references ingested documents against a curated Indian regulatory reference set (Factory Act 1948, OISD, PESO) for a facility area or equipment tag. Returns a covered/partial/gap traffic-light per clause. |
| POST | `/api/compliance/evidence-package` | Given a `regulation_id`, compiles the supporting evidence documents + an AI-generated coverage summary — ready to hand to an auditor. |

> ⚠️ **Not legal advice.** Every response includes a disclaimer; this is a decision-support tool, not a substitute for a qualified compliance officer.

---

## Voice

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/voice/health` | Liveness probe; reports whether Bhashini is configured or the Gemini translation fallback is active. |
| POST | `/api/voice/query` | Upload an audio recording (WAV/WebM/MP3/OGG). Runs STT (faster-whisper, auto language detect) → translate to English (Bhashini, falling back to Gemini) → RAG query → translate answer back → optional TTS. |

**Request:** `multipart/form-data` — `audio` (file, ≤20MB), `role` (form field, optional), `session_id` (form field, optional).

---

## Auth

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/auth/health` | Stub — reports `status: "stub"`. JWT-based auth (`python-jose` + `passlib`) is scaffolded but not yet wired up; see the "Roadmap" section of the root README. |

---

## Error conventions

- Health/liveness endpoints (`/api/*/health`) always return `200` — they report subsystem reachability in the payload rather than failing.
- Upload endpoints validate file type/size and return `415`/`400`/`413` with a `detail` message on bad input.
- Business-logic endpoints (`query`, `rca`, `gap-analysis`, etc.) are designed to degrade gracefully — e.g. a down LLM or graph produces a response with `error` set rather than an HTTP failure — with a `500` reserved as a defensive backstop for genuinely unexpected exceptions.
