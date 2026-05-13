import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from github import Github, GithubException
from app.config import get_settings


def create_repo(idea: dict, log) -> tuple:
    settings = get_settings()
    g = Github(settings.github_token)
    user = g.get_user()

    base = idea["title"].replace(" ", "-")[:50]
    try:
        repo = user.create_repo(
            name=base,
            description=idea["description"][:200],
            private=False,
            auto_init=False,
        )
    except GithubException as e:
        if e.status == 422:
            base = f"{base}-{datetime.now().strftime('%m%d%H%M')}"
            repo = user.create_repo(
                name=base,
                description=idea["description"][:200],
                private=False,
                auto_init=False,
            )
        else:
            raise

    log(f"📁 GitHub repo created: {repo.full_name}")
    return repo, repo.html_url


def push_all(repo, files: list[tuple[str, str]], readme: str, screenshot_path: Path | None, log):
    settings = get_settings()
    token = settings.github_token
    clone_url = f"https://{token}@github.com/{repo.full_name}.git"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Write all project files
        for filename, code in files:
            fp = tmp / filename
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(code, encoding="utf-8")
            log(f"  ↑ {filename}")

        if readme:
            (tmp / "README.md").write_text(readme, encoding="utf-8")
            log("  ↑ README.md")

        if screenshot_path and screenshot_path.exists():
            shutil.copy(screenshot_path, tmp / "screenshot.png")
            log("  ↑ screenshot.png")

        # Git init + commit + push
        def git(*args):
            subprocess.run(["git", *args], cwd=tmp, check=True,
                           capture_output=True, text=True)

        git("init")
        git("config", "user.email", "bot@project-factory.ai")
        git("config", "user.name", "Project Factory")
        git("remote", "add", "origin", clone_url)
        git("add", ".")
        git("commit", "-m", "🤖 Initial commit — auto-generated project")
        git("branch", "-M", "main")
        git("push", "-u", "origin", "main")

    log(f"✅ Pushed to {repo.html_url}")
