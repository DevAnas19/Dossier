# Dossier v2 — AI Research Agent

A multi-agent research pipeline that takes a topic and produces a verified,
structured report — built as a portfolio piece to show an end-to-end agentic
system with claim-level fact verification, not just a single LLM call or a
basic RAG chain.

## What's new in v2

| | v1 | v2 |
|---|---|---|
| Research sources | Web only (Tavily) | Web (Tavily) + Academic (Semantic Scholar) |
| Pipeline shape | Linear — 4 steps in sequence | Planner-first — topic broken into sub-queries before research begins |
| Research strategy | One search, one scrape | Two parallel sources per sub-query, run sequentially with backoff |
| Output unit | Raw report text | Verified claims, each scored supported / contradicted / unresolved |
| Fact checking | None — writer uses whatever the scraper returned | Dedicated verification pass — every claim checked against evidence |
| Failure handling | Any API error crashes the job | Per-agent timeout + retry with exponential backoff on 429 / 503 |
| Progress stages | 4 (search → read → draft → review) | 6 (plan → research → extract → verify → draft → review) |
| UI | Stage ticker + report | Stage ticker + claim summary badges + report |

---

## How v2 works

```
User Question
     │
     ▼
Research Planner          ← breaks the topic into 2 focused sub-queries
     │
     ├── Sub-query 1 ──► Web Search (Tavily)
     │                ──► Academic Search (Semantic Scholar)
     │
     └── Sub-query 2 ──► Web Search (Tavily)
                      ──► Academic Search (Semantic Scholar)
     │
     ▼
Evidence Collection       ← merges all four result blocks
     │
     ▼
Claim Extraction          ← LLM pulls 3–5 discrete, checkable claims
     │
     ▼
Evidence Verification     ← each claim scored: SUPPORTED / CONTRADICTED / UNRESOLVED
     │
     ▼
Synthesis                 ← writer drafts the report from verified claims
     │
     ▼
Critic                    ← second LLM pass reviews for gaps
     │
     ▼
Final Report
```

The key difference from v1: the pipeline verifies before it writes. In v1 the
writer received raw scraped text and had no way to distinguish a well-sourced
fact from a hallucinated one. In v2 every claim is individually checked against
the collected evidence before the writer ever sees it — and the claim summary
badge in the UI makes that visible.

---

## Stack

**Backend:** FastAPI · LangChain · LangGraph · Groq · Tavily · Semantic Scholar API  
**Frontend:** React · Vite

```
research-agent-app/
  backend/
    main.py        FastAPI app — job queue, polling endpoint
    pipeline.py    6-stage orchestration logic
    agents.py      LLM chains + agent builders (planner, extractor, verifier, writer, critic)
    tools.py       web_search (Tavily), academic_search (Semantic Scholar), scrape_url
  frontend/
    src/
      App.jsx      UI — topic form, 6-stage ticker, claim badges, report view
      api.js       polling logic
```

---

## Features

- **Research planning** — the topic is decomposed into sub-queries before any
  search runs, so the evidence pool is broader and less redundant than a single
  query would produce
- **Dual-source research** — Tavily covers recent web results; Semantic Scholar
  covers peer-reviewed papers. Both run for every sub-query. Semantic Scholar
  needs no API key.
- **Claim extraction** — instead of passing raw evidence to the writer, a
  dedicated LLM pass extracts 3–5 atomic, checkable claims from the evidence
- **Evidence verification** — each claim is individually scored against the
  evidence as `SUPPORTED`, `CONTRADICTED`, or `UNRESOLVED` before synthesis
- **Claim summary badge** — the UI shows a ✓ / ✕ / ◌ count above every report
  so it's immediately clear how well-evidenced the output is
- **Rate-limit resilience** — every LLM call goes through a retry wrapper with
  exponential backoff (8s → 16s → 32s → 64s) that handles both 429 and 503
  errors; individual agent calls have a 45s timeout with a graceful fallback so
  one slow source doesn't block the whole job
- **Live progress** — the frontend polls every ~1.2s and the ticker now shows
  all 6 stages: Plan → Research → Extract Claims → Verify → Draft → Review

---

## 1. Run the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then fill in your keys
uvicorn main:app --reload --port 8000
```

Env vars needed in `backend/.env`:

| Variable | Where to get it | Required |
|---|---|---|
| `GROQ_API_KEY` | console.groq.com | Yes |
| `TAVILY_API_KEY` | tavily.com | Yes |
| `GOOGLE_API_KEY` | aistudio.google.com | Optional (Gemini fallback) |
| `GROQ_MODEL` | — | Optional, defaults to `llama-3.3-70b-versatile` |

> **Note on free-tier limits:** Groq's free tier has tight TPM limits. If you
> hit repeated 429s, switch the model by setting `GROQ_MODEL=gemini-2.0-flash`
> and adding a `GOOGLE_API_KEY` — the pipeline works with either provider
> without any code changes.

Check it's up: `http://localhost:8000/api/health`

## 2. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Opens on `http://localhost:5173`. To point it at a different backend, create
`frontend/.env`:

```
VITE_API_URL=http://localhost:8000
```

---

## How the API works

1. `POST /api/research` — submits a topic, starts the pipeline in a background
   thread, returns `{ job_id }` immediately (the pipeline takes 1–3 minutes
   so the request never blocks)
2. `GET /api/research/{job_id}` — returns current status, active stage name,
   and when complete: `report`, `feedback`, and `claim_summary`
   (`{ supported, contradicted, unresolved }`)

Job state lives in an in-memory dict in `main.py` — fine for a single-instance
deployment; swap for Redis if you run multiple backend instances.

---

## 3. Deploying

**Backend (Railway / Render / any long-lived Python host):**
```
Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
```
Set `GROQ_API_KEY` and `TAVILY_API_KEY` as environment variables.  
Note the public URL once deployed.

**Frontend (Vercel / Netlify):**
```
Build command:  npm run build
Output dir:     dist
```
Set `VITE_API_URL` to the deployed backend URL.  
Tighten `allow_origins` in `backend/main.py` from `"*"` to your frontend domain before going live.

---

## Limitations

- Job store is in-memory — restarting the backend loses in-flight jobs
- No auth on the API — add an API key header before exposing this publicly
- Free-tier models (Groq / Gemini) are rate-limited; a burst of requests will
  hit 429s. The retry wrapper handles transient limits but a paid key is
  recommended for demos
- User-document RAG (uploading your own files as a third research source) is
  planned for v3