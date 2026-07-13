# 🏭 Industrial Knowledge Brain (IKB)

> **AI-powered unified intelligence platform for Indian asset-intensive industries.**
> Built for the hackathon — Phases 1–6 fully implemented.

---

## ⚠️ Disclaimer

This platform is a **decision-support tool** built for demonstration and research purposes.

- The **Compliance Gap Tracker** is NOT legal or regulatory advice. All gap findings are illustrative and non-exhaustive. Real compliance audits must be conducted by **qualified compliance officers** familiar with applicable Indian and international regulations (Factory Act 1948, OISD standards, PESO rules, etc.).
- The **Maintenance RCA Agent** provides AI-generated analysis and is NOT a substitute for professional engineering assessment.
- The **Voice Pipeline** uses AI translation and is NOT certified for safety-critical decision making without human verification.

---

## 🎯 What It Does

IKB is a full-stack AI platform that ingests heterogeneous industrial documents (PDFs, maintenance work orders, P&ID drawings, OEM manuals, inspection reports) and powers six intelligent subsystems:

| Phase | Subsystem | Status |
|-------|-----------|--------|
| 1 | Document Ingestion Pipeline | ✅ Complete |
| 2 | Hybrid RAG Chatbot (Knowledge Copilot) | ✅ Complete |
| 3 | P&ID Computer Vision Symbol Detector | ✅ Complete |
| 4 | Multilingual Voice Interaction (Hindi/Tamil/Telugu) | ✅ Complete |
| 5 | Maintenance Intelligence & Root Cause Analysis Agent | ✅ Complete |
| 6 | Compliance Gap Detection Agent | ✅ Complete |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        React Frontend (Vite)                        │
│  Knowledge Copilot │ P&ID Viewer │ Maintenance RCA │ Compliance     │
└───────────────────────────┬────────────────────────────────────────┘
                            │ HTTP / REST
┌───────────────────────────▼────────────────────────────────────────┐
│                    FastAPI Backend (Python 3.11)                    │
│                                                                     │
│  /api/ingest      /api/query      /api/pid-vision                  │
│  /api/voice       /api/maintenance /api/compliance                 │
└──────┬────────────────┬────────────────────────────┬───────────────┘
       │                │                            │
  ChromaDB         Neo4j AuraDB               Gemini 2.5 Flash
  (vector)         (knowledge graph)           (LLM / STT fallback)
                                               faster-whisper (STT)
                                               Bhashini API (TTS/NMT)
```

### Key Technology Choices

| Component | Technology | Why |
|-----------|-----------|-----|
| LLM | Google Gemini 2.5 Flash | Structured JSON output, multilingual, free tier |
| Vector DB | ChromaDB (local persistent) | Zero-infra, fast cosine search |
| Knowledge Graph | Neo4j AuraDB (free tier) | Idempotent MERGE, Cypher traversals |
| STT | faster-whisper (small model) | Local CPU inference, auto language detect |
| Translation | Bhashini NMT + Gemini fallback | Official GoI API, Gemini fallback for resilience |
| CV (P&ID) | OpenCV + skimage skeletonize | No GPU needed, custom contour classifier |
| Agentic Workflow | LangGraph | Stateful multi-node graph for RCA |
| Web Framework | FastAPI | Async, auto-docs, typed schemas |
| Frontend | React + Vite + Tailwind CSS | Fast build, component isolation |

---

## 📚 Documentation

| Doc | Covers |
|-----|--------|
| [`docs/API.md`](docs/API.md) | Every endpoint, request/response shapes, error conventions |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Mermaid diagram source, data flow |
| [`docs/PID_VISION_GUIDE.md`](docs/PID_VISION_GUIDE.md) | P&ID CV detector deep-dive, accuracy notes, manual test checklist |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Common setup issues (Windows `start.bat`, Docker env vars, OCR binaries, Neo4j, ports) |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Project layout, code style, how to add a new subsystem/page |

## 🧹 One-time cleanup (older clones only)

If you're on an older copy of this repo that still has stray `_debug_*.png`
files or a duplicate `generate_sample_pid.py` under `backend/data/sample_documents/`,
run the cleanup script once:
```bash
./scripts/cleanup.sh        # macOS/Linux
scripts\cleanup.bat         # Windows
```
Fresh clones won't have these files at all.

---

## 🚀 Quick Start

### Option A — Docker Compose (recommended — one command, nothing else to install)

Neo4j is bundled by default, so the **only thing you need is a free Gemini API key** — no AuraDB signup required to try the app.

```bash
# 1. Clone and enter
git clone <repo-url>
cd industrial-knowledge-brain

# 2. Set your Gemini key (root .env — this is what docker-compose.yml reads)
cp .env.example .env
# Edit .env and set GEMINI_API_KEY (get one free at https://aistudio.google.com/apikey)

# 3. Launch everything
docker compose up --build
#   — or —
make up

# Frontend → http://localhost:5173
# Backend API → http://localhost:8000
# Swagger docs → http://localhost:8000/docs
# Neo4j Browser → http://localhost:7474  (user: neo4j / password: ikb_password)
```

Or just run `./start.sh` (macOS/Linux) or `start.bat` (Windows) — an interactive
launcher that creates the right `.env` for you and walks you through the choice
of Docker vs. local dev.

> Prefer a managed AuraDB instance over the bundled container? Uncomment and
> fill in `NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` in the root `.env`
> — they override the bundled Neo4j automatically.

Other handy commands (see `Makefile`):
```bash
make logs     # tail all service logs
make health   # check backend + Neo4j + ChromaDB connectivity
make seed     # ingest the bundled sample documents in one shot
make down     # stop everything
make clean    # stop AND wipe Neo4j/Chroma data volumes
```

### Option B — Local Development (no Docker)

**Backend** *(uses the same root `.env` as Docker — see `backend/app/config.py`)*:
```bash
cd backend
pip install -r requirements.txt
# from project root: cp .env.example .env   # fill in GEMINI_API_KEY + Neo4j
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

---

## 🔑 Required Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google AI Studio API key |
| `NEO4J_URI` | Neo4j AuraDB connection URI |
| `NEO4J_USERNAME` | Neo4j username |
| `NEO4J_PASSWORD` | Neo4j password |
| `WHISPER_MODEL_SIZE` | `tiny` / `base` / `small` (default: `small`) |
| `BHASHINI_API_KEY` | Bhashini ULCA key (optional; Gemini fallback used if absent) |
| `BHASHINI_USER_ID` | Bhashini user ID (optional) |

---

## 🧪 How to Test — Phase by Phase

### Phase 1 — Document Ingestion
1. Go to **Swagger UI** at `http://localhost:8000/docs`.
2. Call `POST /api/ingest` and upload any PDF from `backend/data/sample_documents/`.
3. Check the response for entity extraction counts and graph link status.

### Phase 2 — Knowledge Copilot (RAG Chatbot)
1. Open the **Knowledge Copilot** tab.
2. Try: *"What is the vibration trip limit for P-101A?"*
3. Expected: Answer with source citations, confidence badge, and related Neo4j entities.

### Phase 3 — P&ID Vision
1. Open the **P&ID Viewer** tab.
2. Upload `backend/data/sample_documents/sample_pid.png`.
3. Expected: Annotated image with bounding boxes around valves, pumps, tanks, instruments.

### Phase 4 — Voice Interaction
1. Open the **Knowledge Copilot** tab.
2. Click the **microphone icon**, speak in Hindi: *"पी-101ए का वाइब्रेशन लिमिट क्या है?"*
3. Expected: Transcript, detected language badge, English translation, RAG answer, back-translated Hindi response.

### Phase 5 — Maintenance RCA
1. Open **Maintenance & RCA** tab.
2. Enter: *"vibration and oil leakage observed during routine shift rounds"*
3. Expected: Tag auto-resolves to `P-101A`, High risk score, fishbone RCA with Machine/Environment/Method categories citing specific documents.

### Phase 6 — Compliance Tracker
1. Open **Compliance Tracker** tab.
2. Enter: `CDU-1 P-101A`
3. Expected: Traffic-light bar, OISD-154 marked **Covered**, PESO-SCR marked **Gap**, click any row to expand + generate evidence package.

---

## 📁 Project Structure

```
industrial-knowledge-brain/
├── backend/
│   ├── app/
│   │   ├── api/routes/          # FastAPI route handlers
│   │   ├── core/                # Business logic engines
│   │   │   ├── document_parser.py
│   │   │   ├── entity_extractor.py
│   │   │   ├── knowledge_graph.py
│   │   │   ├── vector_store.py
│   │   │   ├── rag_engine.py
│   │   │   ├── pid_detector.py
│   │   │   ├── voice_pipeline.py
│   │   │   ├── rca_agent.py
│   │   │   └── compliance_agent.py
│   │   ├── models/schemas.py
│   │   ├── config.py
│   │   └── main.py
│   ├── scripts/generate_sample_pid.py
│   ├── data/sample_documents/ # sample docs + sample P&ID image
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/pages/
│   │   ├── Dashboard.jsx
│   │   ├── CopilotChat.jsx
│   │   ├── PIDViewer.jsx
│   │   ├── MaintenanceRCA.jsx
│   │   └── ComplianceTracker.jsx
│   ├── src/hooks/         # useTheme, useHealth
│   └── Dockerfile
├── docs/                  # API reference, architecture, guides (see above)
├── scripts/               # one-time repo maintenance scripts
├── docker-compose.yml
├── Makefile
├── CONTRIBUTING.md
└── README.md
```

---

## 🎨 UI/UX

- **Dashboard landing page** — live system health (API/ChromaDB/Neo4j), one-click cards into each subsystem.
- **Dark mode** — toggle in the top-right (or press `D`), persisted across reloads, respects your OS preference by default.
- **Keyboard shortcuts** — `1`–`5` jump between tabs, `D` toggles dark mode.
- **Online/offline indicator** — the nav bar shows live backend reachability so a disconnected API is obvious immediately, not a silent failure.

## 🌟 Hackathon Highlights

1. **Zero-infrastructure vector search** — ChromaDB runs locally, no cloud vector DB needed.
2. **Hybrid retrieval** — Vector similarity (ChromaDB) + graph traversal (Neo4j) for richer, cited answers.
3. **Agentic P&ID vision** — Pure OpenCV + skimage, no ML model weights, runs on CPU.
4. **Bhashini-first, Gemini-fallback voice** — Supports 12+ Indian languages; full STT → translate → RAG → TTS pipeline.
5. **LangGraph RCA** — Multi-node stateful workflow auto-resolves equipment tags from symptom descriptions using vector retrieval.
6. **Compliance with curated Indian regs** — Factory Act 1948, OISD, PESO reference set with honest AI disclaimer.

---

## 📜 License

MIT License.

---

*Built for hackathon demonstration. All regulatory reference data is illustrative and non-exhaustive. This platform is not a certified compliance tool.*
