import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

from app.config import get_settings
from app import database as db
from app.pipeline.orchestrator import run_pipeline, is_running
from app.scheduler import start_scheduler, stop_scheduler

app = FastAPI(title="Project Factory")
templates = Jinja2Templates(directory="app/templates")

settings = get_settings()
data_dir = Path(settings.data_dir)


@app.on_event("startup")
def startup():
    db.init_db()
    start_scheduler()


@app.on_event("shutdown")
def shutdown():
    stop_scheduler()


# ── static screenshots ────────────────────────────────────────────────────────

@app.get("/screenshots/{filename}")
def get_screenshot(filename: str):
    path = data_dir / "screenshots" / filename
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


# ── dashboard ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    runs = db.get_all_runs()
    current = db.get_current_run()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "runs": runs,
            "current": current,
            "is_running": is_running(),
        },
    )


# ── trigger ───────────────────────────────────────────────────────────────────

@app.post("/build")
async def trigger_build(background_tasks: BackgroundTasks):
    if is_running():
        return {"status": "already_running"}
    background_tasks.add_task(run_pipeline)
    return {"status": "started"}


# ── log stream (SSE) ──────────────────────────────────────────────────────────

@app.get("/logs/stream")
async def stream_logs():
    """SSE endpoint: streams log lines of the currently running job."""

    async def generate():
        sent = 0
        while True:
            current = db.get_current_run()
            if current:
                log = current.get("log") or ""
                lines = log.splitlines()
                for line in lines[sent:]:
                    yield f"data: {json.dumps(line)}\n\n"
                sent = len(lines)
                if current["status"] != "running":
                    yield "data: __done__\n\n"
                    return
            await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/logs/{run_id}")
def get_log(run_id: int):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404)
    return {"log": run.get("log", "")}


# ── history API ───────────────────────────────────────────────────────────────

@app.get("/api/runs")
def api_runs():
    return db.get_all_runs()
