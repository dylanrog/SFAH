# Mise (working title)

An AI culinary assistant that teaches cooking judgment — what to make, why it
works, and how to get every dish to the table hot at 7 PM. Inspired by the
principles of *Salt Fat Acid Heat* by Samin Nosrat (the book is credited as
inspiration; no book content is included in this repository).

**Status: Phase 1 — project skeleton.** See [docs/design.md](docs/design.md)
for the full design: architecture, roadmap, and engineering decisions.

## What this will be

- **Cooking Q&A with RAG** — grounded answers with citations over a
  self-authored cooking knowledge base, hybrid vector + full-text search,
  with an automated eval harness.
- **Pantry → dish guidance** — an agent that composes dish directions from
  FlavorGraph ingredient embeddings and salt/fat/acid/heat balance analysis,
  and explains *why* ingredients work together.
- **Timeline scheduler** — "dinner at 7:00": LLM extracts a structured task
  graph, a deterministic critical-path scheduler does all the math.
- **Personal recipe storage** — semantic search over your saved recipes and
  taste-profile-based recommendations.

## Quickstart (backend)

Requires Python 3.12+ and Docker (for the database).

```bash
# database (Postgres 16 + pgvector)
docker compose up -d db

# backend
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"   # Windows
# .venv/bin/python -m pip install -e ".[dev]"          # macOS/Linux

# run checks
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m pytest -q

# run the API  →  http://127.0.0.1:8000/health
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Configuration: copy `backend/.env.example` to `backend/.env`.

## Corpus layout

- `corpus/public/` — self-authored knowledge-base documents (committed; the
  only corpus a public deployment serves).
- `corpus/private/` — gitignored "bring your own documents" directory for
  personal libraries; ingested locally, never committed, never served in
  public mode.

## Credits

- *Salt Fat Acid Heat* (Samin Nosrat) — conceptual inspiration.
- [FlavorGraph](https://github.com/lamypark/FlavorGraph) (Park et al., 2021,
  *Scientific Reports*) — pretrained ingredient embeddings (planned import).
