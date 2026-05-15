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
from app.pipeline.orchestrator import run_pipeline, is_running, VERSION
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
            "version": VERSION,
        },
    )


# ── trigger ───────────────────────────────────────────────────────────────────

@app.post("/build")
async def trigger_build(background_tasks: BackgroundTasks, request: Request):
    if is_running():
        return {"status": "already_running"}
    try:
        prefs = await request.json()
    except Exception:
        prefs = {}
    background_tasks.add_task(run_pipeline, prefs)
    return {"status": "started"}


# ── log stream (SSE) ──────────────────────────────────────────────────────────

@app.get("/logs/stream")
async def stream_logs():
    async def generate():
        sent = 0
        idle = 0
        while idle < 30:
            current = await asyncio.to_thread(db.get_current_run)
            if current:
                idle = 0
                lines = (current.get("log") or "").splitlines()
                for line in lines[sent:]:
                    yield f"data: {json.dumps(line)}\n\n"
                sent = len(lines)
                if current["status"] != "running":
                    yield "data: __done__\n\n"
                    return
            else:
                idle += 1
            await asyncio.sleep(1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
