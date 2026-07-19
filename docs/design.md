# Mise — Design Document

## Overview

Mise is an AI culinary assistant that teaches cooking judgment: what to make from the ingredients on hand, *why* those ingredients work together, and how to get multiple dishes to the table at a target time. It draws on the salt/fat/acid/heat framework popularized by Samin Nosrat's *Salt Fat Acid Heat* (credited as inspiration; no book content is included in this repository).

The product thesis: recipe sites and chat assistants tell you *what* to do, not *why*, and neither can orchestrate a real dinner — multiple dishes, shared equipment, a hard deadline. Mise focuses on the parts of cooking assistance that a raw chat model is structurally bad at:

1. **Deterministic timeline scheduling.** Backward multi-task scheduling under resource constraints is done by a classical algorithm; language models produce plausible-looking but unreliable schedules.
2. **Grounded ingredient pairing.** Pairing suggestions come from published ingredient-embedding data (recipe co-occurrence and shared flavor compounds), with the reasoning shown — not token statistics.
3. **Durable personal state.** Saved recipes, cooking history, and a taste profile persist in a database rather than a context window.

## Scope

### MVP

1. **Cooking Q&A with RAG** — grounded answers with citations over a curated cooking knowledge base; hybrid vector + full-text retrieval; automated evaluation harness.
2. **Pantry → dish guidance** — an agent that composes dish directions from ingredient-embedding data and salt/fat/acid/heat balance analysis, and explains why the combination works.
3. **Timeline scheduler** — natural-language request ("dinner at 7:00") → structured task graphs → critical-path scheduling with resource leveling. All timing math is deterministic.
4. **Personal recipe storage** — structured extraction from pasted recipes, semantic search over the collection, preference-aware recommendations.

### Non-goals (initial release)

Knowledge graphs, image input, collaborative filtering, nutrition data, multi-user auth (single-user until public deployment), mobile/voice, and agent frameworks (the tool-calling loop is hand-rolled — see Design decisions).

## Architecture

```
Next.js (Vercel)                    FastAPI (Railway/Fly.io)
┌─────────────────┐   SSE/REST   ┌──────────────────────────────┐
│ Chat UI          │────────────▶│ /chat  → Agent loop           │
│ Recipe pages     │             │   tools:                      │
│ Timeline Gantt   │             │   ├ retrieve_knowledge (RAG)  │
│ Pantry input     │             │   ├ suggest_pairings          │
└─────────────────┘             │   ├ analyze_balance           │
                                 │   ├ search/save_recipe        │
                                 │   └ build_timeline ──▶ CPM    │
                                 │        scheduler (pure Python)│
                                 └──────────┬───────────────────┘
                                            │
                    ┌───────────────────────┴──────────────┐
                    │ Postgres + pgvector (Neon/Supabase)   │
                    │ relational tables + kb_chunks vectors │
                    │ + FlavorGraph ingredient embeddings   │
                    └───────────────────────────────────────┘
                    LLM: Claude Haiku 4.5 (thin provider adapter)
                    Embeddings: bge-small-en-v1.5 (local, fastembed)
```

### Frontend

Next.js App Router + Tailwind + shadcn/ui. Four screens: chat (SSE streaming, renders citations and structured cards), recipe list/detail, timeline view (Gantt-style bars), pantry input. Server components + fetch; no global state library. The frontend is deliberately thin — the engineering weight is in the backend.

### Backend

FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic migrations, layered `routers/` → `services/` → `repositories/`. The agent loop, retriever, and scheduler live in `services/` as plainly testable Python. SSE streaming for chat; `slowapi` rate limiting on public deployments. Every LLM call is logged with model, token counts, latency, and tool calls.

### Database schema (Postgres + pgvector)

```sql
users(id, email, created_at)                      -- single user until public deploy
recipes(id, user_id, title, description,
        ingredients jsonb, steps jsonb,           -- structured, LLM-extracted
        sfah_notes jsonb,                         -- balance analysis cache
        embedding vector(384), source, created_at)
ingredients(id, name, aliases text[],             -- canonical ingredient table
        flavorgraph_embedding vector(300),        -- imported from FlavorGraph
        category)
kb_documents(id, title, topic, body_md, source_urls text[],
        visibility)                               -- 'public' | 'private'
kb_chunks(id, document_id, content, heading_path,
        embedding vector(384), tsv tsvector)      -- hybrid search
user_events(id, user_id, recipe_id, event_type,   -- save|rate|cooked|dismissed
        value, created_at)
taste_profiles(user_id, centroid vector(384),
        preference_facts jsonb, updated_at)
meal_plans(id, user_id, target_time, recipes jsonb,
        schedule jsonb, created_at)               -- scheduler output, replayable
```

### RAG pipeline

- **Corpus:** curated markdown documents (technique explainers, troubleshooting guides, ingredient notes), each front-mattered with topic and salt/fat/acid/heat tags, written for retrieval (dense, well-scoped chunks).
- **Two corpora, one pipeline:** every document carries a `visibility` flag. The *public* corpus is committed to the repo and is the only corpus a public deployment serves. The *private* corpus is a gitignored `corpus/private/` directory for personal document libraries, ingested locally and retrievable only when the app runs in private mode. Visibility is enforced in the SQL query — not the prompt — and covered by a regression test asserting private chunks can never surface in public mode. This mirrors ACL-aware retrieval in enterprise RAG systems.
- **Ingest:** parse → chunk by heading (~300-500 tokens, heading path prepended) → embed with bge-small-en-v1.5 via fastembed (local ONNX, CPU-friendly) → upsert to `kb_chunks`.
- **Query:** embed query → hybrid search (pgvector cosine + Postgres full-text rank, reciprocal rank fusion) → top-k chunks with scores → answer with chunk-ID citations. Below a score threshold, the model states it lacks grounded material instead of free-associating.
- **Evaluation:** a golden set of question → expected-source pairs; measured retrieval hit@5 and LLM-judged answer faithfulness, run in CI with results published in the README.

### Ingredient intelligence

[FlavorGraph](https://github.com/lamypark/FlavorGraph) (Park et al., 2021, *Scientific Reports*) provides pretrained 300-dimension ingredient embeddings learned from recipe co-occurrence and shared flavor compounds (~7k ingredients). A one-time import script loads them into `ingredients.flavorgraph_embedding` with alias normalization ("scallion" → "green onion"). This powers pairing suggestions (nearest neighbors), pantry-set analysis (which subsets cohere; which single addition bridges them), and category-filtered substitutions.

Two embedding spaces coexist deliberately: FlavorGraph (300-dim, flavor chemistry and co-occurrence) for ingredients, and bge (384-dim, text semantics) for recipes and knowledge. They measure different kinds of similarity and are never mixed.

### The salt/fat/acid/heat framework

1. **Ontology:** knowledge-base documents, recipe analyses, and coaching output are tagged and structured along the four axes.
2. **`analyze_balance` tool:** given a dish's ingredients and method, the LLM fills a Pydantic schema — `{salt: {sources, timing, assessment}, fat: {...}, acid: {present?, suggestion}, heat: {method, matches_ingredient?}}` — rendered as a "balance card" in the UI. This is how "explain why it works" becomes concrete rather than vibes.
3. **Persona:** the system prompt encodes a principles-over-recipes coaching philosophy, written originally for this project.

### Agent design

A hand-rolled tool-calling loop (~100-150 lines) on the Anthropic SDK: send messages + tool schemas; on `tool_use`, execute, append the result, repeat; capped iterations and a per-request token budget; every step logged. Tools (Pydantic-schema'd): `retrieve_knowledge`, `suggest_pairings`, `analyze_balance`, `search_recipes`, `save_recipe`, `build_timeline`, `get_taste_profile`. Malformed tool arguments round-trip the validation error to the model once, then degrade gracefully.

### Personalization

Explicit events (save, rate, cooked) feed a taste profile: an embedding centroid of liked recipes plus extracted preference facts ("dislikes cilantro", "weeknights under 45 minutes"). Recommendations are content-based — cosine similarity against the centroid, filtered by facts — and always shown with their reasoning.

### The scheduler

The clearest example of dividing labor between the LLM and classical code:

- **LLM (structured output):** recipe text → `TimelineTask[]`: `{id, name, duration_min, depends_on[], resource: oven|stovetop|hands_on|passive, holds_well, hold_max_min}`, Pydantic-validated.
- **Algorithm (pure Python, zero LLM):** merge task graphs across dishes → cycle detection → backward pass from the target finish time (critical-path method) → resource leveling (one oven, two burners, one pair of hands; `holds_well` tasks absorb slack) → start times, critical path, and honest warnings ("oven contention 5:40-6:10; the potatoes hold, pull them early").
- **LLM again:** renders the computed schedule as friendly prose. Every number comes from the algorithm.

The scheduler is pure functions, verified with property-based tests (no task before its dependencies; resources never over-committed; everything lands by the deadline).

## Design decisions

- **pgvector over a dedicated vector database.** At this scale (<100k vectors), a dedicated vector DB adds an operational dependency and a network hop for no benefit. pgvector allows one SQL query to combine vector similarity, full-text rank, and relational filters, with a single backup story.
- **Hand-rolled agent loop over a framework.** The loop is small, and owning it means owning error handling, iteration caps, token budgets, and observability directly.
- **The LLM never does timing math.** Language models are unreliable at constrained scheduling; the LLM parses and presents, the algorithm computes.
- **Visibility enforced in SQL, not prompts.** Corpus access control belongs in the query layer where it can be regression-tested, not in instructions a model might ignore.
- **Content-based recommendations, not collaborative filtering.** A single-user system has no user-user signal; collaborative filtering would be cold-start theater.
- **Local embedding model.** bge-small-en-v1.5 via fastembed runs on CPU at zero marginal cost, removing a per-query external dependency.
- **Licensing-aware data sourcing.** Large recipe datasets (Recipe1M, RecipeNLG) carry research-only licenses, and popular recipe-site scrapes are legally murky, so the pantry flow is generative-first — composed from ingredient-pairing data and principles — matched against a small curated seed set and the user's own saved recipes. The knowledge corpus is originally authored; FlavorGraph is openly published research, cited.

### Related work

[Epicure](https://epicure.kaikaku.ai) (Kaikaku) is a computational-gastronomy web app built on a 300-dimension ingredient model — validation that ingredient-embedding products work, and a UI reference for pairing exploration. Mise integrates the underlying class of data (FlavorGraph) directly rather than depending on a third-party app.

## Roadmap

**Phase 1 — working skeleton (weeks 1-2).** Repo scaffold (FastAPI, Postgres via docker-compose, Alembic, pytest, ruff, CI). Recipe CRUD. First ~30 knowledge-base documents. Ingest pipeline + hybrid retrieval + `/ask` endpoint with citations. Minimal chat page. *Milestone: grounded Q&A with citations.*

**Phase 2 — AI pipeline depth (weeks 3-5).** Agent loop + tools. FlavorGraph import, pairing tools, pantry flow with balance cards. Scheduler (extraction schema, CPM + resource leveling, property tests, timeline UI). SSE streaming. Evaluation harness in CI. Corpus to 60+ documents. *Milestone: full pantry → dish → schedule flow.*

**Phase 3 — personalization + deployment (weeks 6-8).** Events, taste profile, recommendations with reasoning. Auth + rate limiting. Deploy (Vercel + Railway/Fly + Neon). Documentation, demo video, engineering writeup. *Stretch:* ingredient-substitution graph (NetworkX over FlavorGraph edges); photo → pantry-list input.

Each phase ends in a demonstrable state.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2, Alembic | Async, typed, structured-output-native |
| DB | Postgres 16 + pgvector | One DB for relational + vector + full-text |
| LLM | Claude Haiku 4.5 behind a thin adapter | Strong tool calling + structured outputs at hobby-scale cost; adapter keeps the provider swappable |
| Embeddings | bge-small-en-v1.5 via fastembed (local ONNX) | Zero marginal cost, no per-query API dependency |
| Ingredient data | FlavorGraph pretrained embeddings | Openly published research artifact |
| Agent | Hand-rolled loop on the Anthropic SDK | Small, observable, fully owned |
| Evals | Golden set + LLM-as-judge, pytest-integrated | Quality measured, not assumed |
| Frontend | Next.js + Tailwind + shadcn/ui, SSE | Thin, modern, demo-friendly |
| Testing | pytest, Hypothesis (scheduler), ruff, GitHub Actions | Property-based tests where correctness is algorithmic |
| Deploy | Vercel + Railway/Fly.io + Neon | Free/hobby tiers |

## User flows

**Pantry → dish.** "I have chicken thighs, lemon, yogurt, garlic, and rice — what can I make?" → ingredients normalized against the canonical table → `suggest_pairings` (yogurt-garlic-lemon cluster tightly in FlavorGraph space) → two or three dish directions composed → `analyze_balance` on the lead → response: the dish, *why it works* ("yogurt is the fat vehicle and a tenderizing acid; add lemon late — acid cooked long goes flat"), a balance card, and offers to save or schedule.

**Cooking question.** "Why did my sauce break?" → `retrieve_knowledge` → hybrid search returns emulsion chunks → grounded answer with expandable citations plus a diagnostic follow-up ("was the butter added quickly over high heat?"). Out-of-corpus questions get an explicit "not in my knowledge base" with any general answer clearly labeled ungrounded.

**Timeline.** "Roast chicken, potatoes, green beans — dinner at 7:00." → `build_timeline` per dish (LLM extraction → task DAGs) → merged CPM + resource leveling → schedule JSON → Gantt render + prose plan, with honest warnings when constraints can't be met ("the start time was 20 minutes ago — here's the compressed plan").

**Save & retrieve.** Paste a family recipe → structured extraction (user confirms) → embedded and stored → later, "that soup with the parmesan rind" matches semantically with no keyword overlap → save/rate/cooked events nudge the taste profile → future suggestions skew toward it, reasoning shown.

## Verification

- **Phase 1:** `docker compose up` + dev server run clean; `pytest` green in CI; `/ask` returns cited answers in the browser.
- **Phase 2:** end-to-end demo script (pantry → dish + balance card → "dinner at 7" → correct Gantt, spot-checked by hand); Hypothesis suite green on the scheduler; eval run reports hit@5 and faithfulness against thresholds; visibility regression test green (private chunks unreachable in public mode).
- **Phase 3:** live deployment survives a stranger clicking around under rate limits; the save → profile → recommendation loop is observable in the UI; the README quickstart works on a clean machine.
