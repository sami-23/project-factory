import base64
from datetime import datetime
from pathlib import Path

from github import Github, GithubException
from app.config import get_settings


def create_repo(idea: dict, log) -> tuple:
    """Creates the GitHub repo. Returns (repo_obj, html_url)."""
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
    """Pushes all files as a single git commit using the Git Data API."""
    blobs = []

    for filename, code in files:
        b = repo.create_git_blob(code, "utf-8")
        blobs.append(InputGitTreeElement(filename, "100644", "blob", b.sha))
        log(f"  ↑ {filename}")

    if readme:
        b = repo.create_git_blob(readme, "utf-8")
        blobs.append(InputGitTreeElement("README.md", "100644", "blob", b.sha))
        log("  ↑ README.md")

    if screenshot_path and screenshot_path.exists():
        with open(screenshot_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        b = repo.create_git_blob(encoded, "base64")
        blobs.append(InputGitTreeElement("screenshot.png", "100644", "blob", b.sha))
        log("  ↑ screenshot.png")

    tree = repo.create_git_tree(blobs)
    commit = repo.create_git_commit("🤖 Initial commit — auto-generated project", tree, [])
    repo.create_git_ref("refs/heads/main", commit.sha)
    log(f"✅ Pushed to {repo.html_url}")


# PyGithub's InputGitTreeElement lives in github.InputGitTreeElement
try:
    from github import InputGitTreeElement
except ImportError:
    from github.InputGitTreeElement import InputGitTreeElement
