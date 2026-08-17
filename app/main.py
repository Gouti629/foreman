"""FastAPI app: serves the dashboard and a small JSON API over submissions
and run traces. Submission fixtures — and pre-computed live run results, if
present — are loaded into SQLite on startup so the dashboard has something
to show even before any live run happens.
"""
import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db import (
    get_conn, get_run, get_submission, init_db, list_runs, list_submissions,
    save_run, upsert_submission,
)
from app.run_pipeline import run_submission

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBMISSIONS_FIXTURE = os.path.join(BASE_DIR, "data", "submissions", "submissions.json")
SEED_RUNS_FIXTURE = os.path.join(BASE_DIR, "data", "runs", "seed_runs.json")
DASHBOARD_DIR = os.path.join(BASE_DIR, "dashboard")

app = FastAPI(title="Foreman")


@app.on_event("startup")
def _startup():
    init_db()
    if os.path.exists(SUBMISSIONS_FIXTURE):
        with open(SUBMISSIONS_FIXTURE, encoding="utf-8") as f:
            fixtures = json.load(f)
        with get_conn() as conn:
            for sub in fixtures:
                upsert_submission(conn, sub)
    if os.path.exists(SEED_RUNS_FIXTURE):
        with open(SEED_RUNS_FIXTURE, encoding="utf-8") as f:
            seed_runs = json.load(f)
        with get_conn() as conn:
            for run in seed_runs:
                save_run(conn, run)


app.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))


@app.get("/api/submissions")
def api_list_submissions():
    with get_conn() as conn:
        submissions = list_submissions(conn)
        latest_runs = {r["submission_id"]: r for r in list_runs(conn)}
    out = []
    for sub in submissions:
        run = latest_runs.get(sub["submission_id"])
        out.append({
            "submission_id": sub["submission_id"],
            "business_name": sub["business_name"],
            "business_type": sub["business_type"],
            "industry_class_code": sub["industry_class_code"],
            "known_label": sub.get("known_label"),
            "latest_run_id": run["run_id"] if run else None,
            "latest_decision": run["decision"]["decision"] if run else None,
        })
    return out


@app.get("/api/submissions/{submission_id}")
def api_get_submission(submission_id: str):
    with get_conn() as conn:
        sub = get_submission(conn, submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="submission not found")
    return sub


@app.get("/api/runs")
def api_list_runs():
    with get_conn() as conn:
        return list_runs(conn)


@app.get("/api/runs/{run_id}")
def api_get_run(run_id: str):
    with get_conn() as conn:
        run = get_run(conn, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.post("/api/submissions/{submission_id}/run")
async def api_run_submission(submission_id: str):
    with get_conn() as conn:
        sub = get_submission(conn, submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="submission not found")
    trace = await run_submission(sub)
    return trace
