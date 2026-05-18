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

settings = get_settings()
data_dir = Path(settings.data_dir)

app = FastAPI(title="Project Factory")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def startup():
    db.init_db()
    db.cleanup_stuck_runs()  # any 'running' from before this restart → 'failed'
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


# ── run management ───────────────────────────────────────────────────────────

@app.delete("/runs/{run_id}")
def delete_run(run_id: int):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404)
    if run["status"] == "running":
        raise HTTPException(400, "Cannot delete a run that is currently in progress")
    if run.get("screenshot_path"):
        try:
            Path(run["screenshot_path"]).unlink(missing_ok=True)
        except Exception:
            pass
    db.delete_run(run_id)
    return {"status": "deleted"}


@app.post("/runs/{run_id}/retry")
async def retry_run(run_id: int, background_tasks: BackgroundTasks):
    if is_running():
        return {"status": "already_running"}
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404)
    if not run.get("idea_json"):
        raise HTTPException(400, "No idea data stored for this run — trigger a fresh build instead")
    retry_idea = json.loads(run["idea_json"])
    background_tasks.add_task(run_pipeline, None, retry_idea)
    return {"status": "started"}


# ── log stream (SSE) ──────────────────────────────────────────────────────────

@app.get("/logs/stream")
async def stream_logs():
    async def generate():
        sent = 0
        heartbeat = 0

        # Wait up to 5s for the pipeline to actually start
        for _ in range(5):
            if is_running():
                break
            await asyncio.sleep(1)

        if not is_running():
            yield "data: __done__\n\n"
            return

        # Stream while the pipeline is running
        while is_running():
            current = await asyncio.to_thread(db.get_current_run)
            if current:
                lines = (current.get("log") or "").splitlines()
                for line in lines[sent:]:
                    yield f"data: {json.dumps(line)}\n\n"
                    heartbeat = 0
                sent = len(lines)
            heartbeat += 1
            if heartbeat >= 15:
                yield ": heartbeat\n\n"  # keeps proxy from closing idle connection
                heartbeat = 0
            await asyncio.sleep(1)

        # Pipeline finished — drain any final log lines then signal done
        last = await asyncio.to_thread(db.get_last_run)
        if last:
            lines = (last.get("log") or "").splitlines()
            for line in lines[sent:]:
                yield f"data: {json.dumps(line)}\n\n"
        yield "data: __done__\n\n"

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
