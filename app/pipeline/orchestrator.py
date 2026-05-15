import asyncio
import subprocess
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


def _get_version() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip()
    except Exception:
        return "dev"


VERSION = _get_version()

_running = False


def is_running() -> bool:
    return _running


async def run_pipeline(prefs: dict | None = None):
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

    # Wrap every blocking call so the event loop stays free for SSE streaming.
    # asyncio.wait_for adds a hard timeout so a hung API call fails loudly.
    async def T(fn, *args, timeout=300):
        return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=timeout)

    try:
        log(f"🚀 Pipeline started — {today} | git:{VERSION}")

        # 1. Idea (blocking: Anthropic HTTP call)
        idea = await T(generate_idea, log, prefs or {})
        db.update_run(
            run_id,
            title=idea["title"],
            description=idea["description"],
            language=idea["language"],
            project_type=idea["project_type"],
        )

        # 2. Code generation (blocking: OpenAI + Anthropic HTTP calls)
        files = await T(generate_code, idea, log, timeout=480)

        # 3. Test + screenshot
        screenshot_dir = Path(settings.data_dir) / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"{run_id}.png"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            for filename, code in files:
                fp = tmp / filename
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(code, encoding="utf-8")

            # If the declared entry_point wasn't generated, find the real one
            if not (tmp / idea["entry_point"]).exists():
                generated = [f[0] for f in files]
                log(f"⚠️  entry_point '{idea['entry_point']}' missing — generated: {generated}")
                ep_name = Path(idea["entry_point"]).name
                match = next((f for f in generated if Path(f).name == ep_name), None)
                if match is None:
                    for candidate in ("server.js", "app.js", "index.js", "main.js",
                                      "server.py", "app.py", "main.py"):
                        match = next((f for f in generated if Path(f).name == candidate), None)
                        if match:
                            break
                if match is None and generated:
                    match = generated[0]
                if match:
                    idea = {**idea, "entry_point": match}
                    log(f"📌 Adjusted entry_point → '{match}'")

            # blocking: subprocess + time.sleep polling
            success, stdout, stderr = await T(run_project, idea, tmp, log)

            if not success:
                log("❌ Project failed to run — aborting, no GitHub repo created")
                db.update_run(run_id, status="failed")
                return

            # async: Playwright
            await take_screenshot(idea, tmp, stdout, screenshot_path, log)

        db.update_run(
            run_id,
            screenshot_path=str(screenshot_path) if screenshot_path.exists() else None,
        )

        # 4. Create GitHub repo (blocking: PyGithub HTTP call)
        repo, github_url = await T(create_repo, idea, log)
        db.update_run(run_id, github_url=github_url)

        # 5. Write README (blocking: Anthropic HTTP call)
        readme = await T(write_readme, idea, files, stdout, github_url, log)

        # 6. Push (blocking: git subprocess)
        await T(push_all, repo, files, readme, screenshot_path if screenshot_path.exists() else None, log)

        db.update_run(run_id, status="success")
        log(f"🎉 Done! {github_url}")

    except Exception as e:
        log(f"💥 Pipeline failed: {type(e).__name__}: {e}")
        db.update_run(run_id, status="failed")
        raise
    finally:
        _running = False
