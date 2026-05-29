import asyncio
import json
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from app.config import get_settings
from app import database as db
from app.pipeline.ideator import generate_idea
from app.pipeline.planner import plan_project
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
        pass
    # Walk up from this file looking for the VERSION file
    p = Path(__file__).resolve()
    for _ in range(6):
        p = p.parent
        candidate = p / "VERSION"
        if candidate.exists():
            try:
                return candidate.read_text().strip()
            except Exception:
                break
    return "unknown"


VERSION = _get_version()

_running = False


def is_running() -> bool:
    return _running


_PLAN_TIMEOUTS = {"minimal": 90,  "standard": 120, "large": 180}
_GEN_TIMEOUTS  = {"minimal": 600, "standard": 600, "large": 1200}


def _load_project_files(project_dir: Path) -> list[tuple[str, str]]:
    """Read all source files from a persisted project directory."""
    skip_names = {"README.md", "screenshot.png"}
    files = []
    for fp in sorted(project_dir.rglob("*")):
        if fp.is_file() and fp.name not in skip_names and fp.suffix != ".png":
            rel = str(fp.relative_to(project_dir)).replace("\\", "/")
            try:
                files.append((rel, fp.read_text(encoding="utf-8")))
            except Exception:
                pass
    return files


def _find_entry_point(idea: dict, files: list[tuple[str, str]], log) -> dict:
    """Adjust idea['entry_point'] if the declared file is missing."""
    generated = [f[0] for f in files]
    if not any(Path(f) == Path(idea["entry_point"]) for f in generated):
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
            log(f"⚠️  entry_point '{idea['entry_point']}' missing — adjusted → '{match}'")
            return {**idea, "entry_point": match}
    return idea


async def retest_pipeline(run_id: int):
    """Re-run test → screenshot → GitHub using existing saved files. No AI calls."""
    global _running
    if _running:
        return
    _running = True

    settings = get_settings()
    db.update_run(run_id, status="running", log="")

    def log(msg: str):
        print(msg, flush=True)
        db.append_log(run_id, msg)

    async def T(fn, *args, timeout=300):
        return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=timeout)

    try:
        run = db.get_run(run_id)
        if not run or not run.get("idea_json"):
            log("❌ No idea data stored for this run — use Full Rebuild instead")
            db.update_run(run_id, status="failed")
            return

        idea = json.loads(run["idea_json"])
        log(f"🔄 Retesting: \"{idea['title']}\" (using saved files, no AI)")

        project_dir = Path(settings.data_dir) / "projects" / str(run_id)
        if not project_dir.exists():
            log("❌ No saved files found — use Full Rebuild instead")
            db.update_run(run_id, status="failed")
            return

        files = _load_project_files(project_dir)
        log(f"📂 Loaded {len(files)} file(s): {', '.join(f[0] for f in files)}")

        screenshot_dir = Path(settings.data_dir) / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"{run_id}.png"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            for filename, code in files:
                fp = tmp / filename
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(code, encoding="utf-8")

            idea = _find_entry_point(idea, files, log)
            success, stdout, stderr = await T(run_project, idea, tmp, log)

            if not success:
                log("❌ Project failed to run — aborting")
                db.update_run(run_id, status="failed")
                return

            await take_screenshot(idea, tmp, stdout, screenshot_path, log)

        db.update_run(
            run_id,
            screenshot_path=str(screenshot_path) if screenshot_path.exists() else None,
        )

        # Only publish to GitHub if not already done
        if not run.get("github_url"):
            repo, github_url = await T(create_repo, idea, log)
            db.update_run(run_id, github_url=github_url)
            readme = await T(write_readme, idea, files, stdout, github_url, log)
            if readme:
                (project_dir / "README.md").write_text(readme, encoding="utf-8")
            await T(push_all, repo, idea, files, readme,
                    screenshot_path if screenshot_path.exists() else None, log)
            db.update_run(run_id, status="success")
            log(f"🎉 Done! {github_url}")
        else:
            db.update_run(run_id, status="success")
            log(f"🎉 Done! (already on GitHub: {run['github_url']})")

    except Exception as e:
        log(f"💥 Retest failed: {type(e).__name__}: {e}")
        db.update_run(run_id, status="failed")
        raise
    finally:
        _running = False


async def run_pipeline(prefs: dict | None = None, retry_idea: dict | None = None):
    global _running
    if _running:
        return
    _running = True

    today = date.today().isoformat()
    run_id = db.create_run(today)
    settings = get_settings()

    # Auto builds (prefs=None, not a retry) default to minimal
    if prefs is None and retry_idea is None:
        prefs = {"size": "minimal"}
    prefs = prefs or {}
    size = prefs.get("size", "standard")

    def log(msg: str):
        print(msg, flush=True)
        db.append_log(run_id, msg)

    # Wrap every blocking call so the event loop stays free for SSE streaming.
    # asyncio.wait_for adds a hard timeout so a hung API call fails loudly.
    async def T(fn, *args, timeout=300):
        return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=timeout)

    try:
        log(f"🚀 Pipeline started — {today} | v{VERSION} | size={size}")

        # 1. Idea — skip if retrying a known idea
        if retry_idea:
            idea = retry_idea
            log(f"🔄 Retrying: \"{idea['title']}\" ({idea['language']}, {idea['project_type']})")
        else:
            idea = await T(generate_idea, log, prefs)

        db.update_run(
            run_id,
            title=idea["title"],
            description=idea["description"],
            language=idea["language"],
            project_type=idea["project_type"],
            category=idea.get("category"),
            tech_stack=json.dumps(idea.get("tech_stack", [])),
            idea_json=json.dumps(idea),
            build_size=size,
        )

        # 2. Architecture planning (blocking: Anthropic HTTP call)
        plan, plan_cost = await T(plan_project, idea, log, prefs,
                                  timeout=_PLAN_TIMEOUTS[size])
        db.update_run(run_id, plan_text=plan)

        # 3. Code generation — Claude Opus implements the plan (blocking: Anthropic HTTP call)
        files, gen_cost = await T(generate_code, idea, log, prefs, plan,
                                  timeout=_GEN_TIMEOUTS[size])

        total_cost = plan_cost + gen_cost
        db.update_run(run_id, cost_usd=round(total_cost, 4))

        # Persist files to data dir so they can be downloaded later
        project_dir = Path(settings.data_dir) / "projects" / str(run_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        for fname, code in files:
            fp = project_dir / fname
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(code, encoding="utf-8")

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

            idea = _find_entry_point(idea, files, log)

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
        if readme:
            (project_dir / "README.md").write_text(readme, encoding="utf-8")

        # 6. Push (blocking: git subprocess)
        await T(push_all, repo, idea, files, readme, screenshot_path if screenshot_path.exists() else None, log)

        db.update_run(run_id, status="success")
        log(f"🎉 Done! {github_url}")

    except Exception as e:
        log(f"💥 Pipeline failed: {type(e).__name__}: {e}")
        db.update_run(run_id, status="failed")
        raise
    finally:
        _running = False
