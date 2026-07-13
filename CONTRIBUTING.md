# Contributing

## Project layout

```
industrial-knowledge-brain/
├── backend/           FastAPI app — see backend/app/{api,core,models}
├── frontend/          React + Vite + Tailwind
├── docs/              Architecture, API reference, testing, troubleshooting
├── scripts/           One-off maintenance scripts (cleanup, etc.)
├── docker-compose.yml One-command local stack (backend + frontend + Neo4j)
└── Makefile           Convenience wrappers around docker compose
```

## Setting up for development

See the root [README](./README.md) "Quick Start" section — Docker Compose is
the fastest path; local (no-Docker) setup is documented as Option B.

## Code style

- **Backend**: type-hinted Python, docstrings on every public class/function,
  Google-style. Every route degrades gracefully rather than raising a bare
  500 where reasonably possible — failures are reported in structured JSON
  (`{"error": "..."}` fields) so a down dependency (Neo4j, Gemini, etc.)
  doesn't take the whole endpoint down.
- **Frontend**: functional components + hooks, Tailwind utility classes
  (no CSS-in-JS). Keep new "structural" colors within the existing slate
  palette so the global dark-mode override in `src/index.css` keeps working
  without per-component `dark:` variants — see the comment block at the top
  of that file before introducing new neutral background/text colors.

## Adding a new subsystem/page

1. Backend: add a route module under `app/api/routes/`, a `core/` module for
   the business logic, and Pydantic schemas in `app/models/schemas.py`.
   Register the router in `app/main.py`.
2. Frontend: add a page under `src/pages/`, then register it in the `PAGES`
   map in `src/App.jsx` (icon from `lucide-react`, plus a route key).
3. Document the new endpoint(s) in `docs/API.md`.
4. If it needs a new environment variable, add it to the root `.env.example`
   (and `docker-compose.yml`'s `environment:` block if container-specific).

## Testing

There's no formal test suite yet (see Roadmap in the README) — current
verification is manual, walked through per-subsystem in `docs/API.md` and
`docs/PID_VISION_GUIDE.md`. If you add `pytest` tests, put them under
`backend/tests/` and wire a `make test` target into the `Makefile`.

## Commit hygiene

- Don't commit `.env` — only the root `.env.example` template.
- Don't commit anything under `backend/data/chroma_persist/` (local vector
  store state) or IDE folders (`.idea/`, `.vscode/`) — already gitignored.
