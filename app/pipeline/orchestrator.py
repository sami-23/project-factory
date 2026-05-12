import asyncio
import sys
import tempfile
from datetime import date
from pathlib import Path

from app.config import get_settings
from app import database as db
from app.pipeline.ideator import generate_idea
from app.pipeline.builder import generate_code
from app.pipeline.tester import run_project
from app.pipeline.screenshotter import take_screenshot
from app.pipeline.readme_writer import write_readme
from app.pipeline.publisher import create_repo, push_all

_running = False


def is_running() -> bool:
    return _running


async def run_pipeline():
    global _running
    if _running:
        return
    _running = True

    today = date.today().isoformat()
    run_id = db.create_run(today)
    settings = get_settings()

    def log(msg: str):
        print(msg, flush=True)
        db.append_log(run_id, msg)

    try:
        log(f"🚀 Pipeline started — {today}")

        # 1. Idea
        idea = generate_idea(log)
        db.update_run(
            run_id,
            title=idea["title"],
            description=idea["description"],
            language=idea["language"],
            project_type=idea["project_type"],
        )

        # 2. Code generation
        files = generate_code(idea, log)

        # 3. Write files to temp dir, test, screenshot — all in one tmpdir
        screenshot_dir = Path(settings.data_dir) / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"{run_id}.png"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            for filename, code in files:
                fp = tmp / filename
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(code, encoding="utf-8")

            success, stdout, stderr = run_project(idea, tmp, log)
            await take_screenshot(idea, tmp, stdout, screenshot_path, log)

        db.update_run(
            run_id,
            screenshot_path=str(screenshot_path) if screenshot_path.exists() else None,
        )

        # 4. Create GitHub repo first (need URL for README)
        repo, github_url = create_repo(idea, log)
        db.update_run(run_id, github_url=github_url)

        # 5. Write README with real URL
        readme = write_readme(idea, files, stdout, github_url, log)

        # 6. Push everything in one commit
        push_all(repo, files, readme, screenshot_path if screenshot_path.exists() else None, log)

        db.update_run(run_id, status="success")
        log(f"🎉 Done! {github_url}")

    except Exception as e:
        log(f"💥 Pipeline failed: {type(e).__name__}: {e}")
        db.update_run(run_id, status="failed")
        raise
    finally:
        _running = False
