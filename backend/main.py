import uuid
import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pipeline import run_research_pipeline

app = FastAPI(title="Research Agent API")

# In dev this allows any origin; lock this down to your deployed frontend's
# domain before shipping to production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STAGE_NAMES = {
    1: "Searching the web",
    2: "Reading top source",
    3: "Drafting report",
    4: "Reviewing report",
}

# Simple in-memory job store. Fine for a single-instance deployment / demo;
# swap for Redis or a DB if you ever need multiple backend instances.
jobs: dict[str, dict] = {}


class ResearchRequest(BaseModel):
    topic: str


def _run_job(job_id: str, topic: str):
    def on_update(step_index, step_name, status, detail):
        jobs[job_id]["stage"] = step_index
        jobs[job_id]["stage_name"] = STAGE_NAMES.get(step_index, step_name)
        jobs[job_id]["stage_status"] = status
        jobs[job_id]["updated_at"] = time.time()

    try:
        result = run_research_pipeline(topic, on_update=on_update)
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["report"] = result["report"]
        jobs[job_id]["feedback"] = result["feedback"]
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@app.post("/api/research")
def start_research(req: ResearchRequest):
    if not req.topic or not req.topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "running",
        "topic": req.topic,
        "stage": 0,
        "stage_name": "Queued",
        "stage_status": "running",
        "created_at": time.time(),
    }

    thread = threading.Thread(target=_run_job, args=(job_id, req.topic), daemon=True)
    thread.start()

    return {"job_id": job_id}


@app.get("/api/research/{job_id}")
def get_research_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/health")
def health():
    return {"status": "ok"}
