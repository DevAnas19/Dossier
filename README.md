# Dossier — AI Research Agent

A multi-agent research pipeline that takes a topic and produces a structured,
cited report — built as a portfolio piece to show an end-to-end agentic
system, not just a single LLM call.

**Pipeline:** a search agent (Tavily) gathers sources → a reader agent scrapes
the most relevant one → a writer chain drafts a structured report → a critic
chain reviews it for accuracy and gaps. All four stages run through Groq-hosted
open models via LangChain/LangGraph.

**Stack:** FastAPI (backend/API) · React + Vite (frontend) · LangChain /
LangGraph · Groq · Tavily

```
research-agent-app/
  backend/     FastAPI + LangChain/LangGraph pipeline
  frontend/    React (Vite) UI
```

## Features

- Live progress: the UI polls the backend and updates a 4-stage ticker
  (search → read source → draft → review) as the pipeline runs
- Structured output: findings render as a real table (finding + evidence),
  not a wall of text
- Editor pass: a critic agent scores the report and lists concrete revisions
  before you see the final version

## 1. Run the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then fill in your real keys
uvicorn main:app --reload --port 8000
```

Env vars needed in `backend/.env`:
- `GROQ_API_KEY` — from console.groq.com
- `TAVILY_API_KEY` — from tavily.com
- `GROQ_MODEL` — optional, defaults to `openai/gpt-oss-120b`

Check it's up: `http://localhost:8000/api/health`

## 2. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Opens on `http://localhost:5173` and talks to the backend at
`http://localhost:8000` by default. To point it elsewhere, create
`frontend/.env`:

```
VITE_API_URL=http://localhost:8000
```

## How it works

1. You submit a topic — the frontend calls `POST /api/research`, which kicks
   off the pipeline in a background thread and returns a `job_id` right away
   (the pipeline itself takes a minute or two, so the request doesn't block).
2. The frontend polls `GET /api/research/{job_id}` every ~1.2s and updates
   the stage ticker as the backend reports progress.
3. When `status` flips to `completed`, the report and the critic's review
   render as a document.

Job state lives in memory in `main.py` (a plain dict) — fine for a
single-instance deployment; swap for Redis or a database if this ever runs
behind multiple backend instances.

## 3. Deploying

**Backend (Railway or any host that runs a long-lived Python process):**
- New project → deploy from the `backend/` folder (or a repo containing it)
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Set `GROQ_API_KEY` and `TAVILY_API_KEY` as environment variables on the host
- Note the public URL once deployed (e.g. `https://your-app.up.railway.app`)

**Frontend (Vercel or Netlify):**
- Import the `frontend/` folder as the project root
- Build command: `npm run build`, output dir: `dist`
- Set an environment variable `VITE_API_URL` to the deployed backend URL
- Before going live, tighten `allow_origins` in `backend/main.py` from `"*"`
  to the actual frontend domain

## Limitations

- Job store is in-memory — restarting the backend loses in-flight jobs
- No auth on the API — add an API key header before exposing this publicly
- Groq's free tier is rate-limited; a burst of requests will 429