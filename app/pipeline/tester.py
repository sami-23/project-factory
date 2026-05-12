import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path


def run_project(idea: dict, tmpdir: Path, log) -> tuple[bool, str, str]:
    lang = idea["language"]
    if lang == "python":
        return _run_python(idea, tmpdir, log)
    elif lang == "javascript":
        return _run_node(idea, tmpdir, log)
    return False, "", f"Unsupported language: {lang}"


def _install_python_deps(tmpdir: Path, log):
    req = tmpdir / "requirements.txt"
    if not req.exists():
        return
    log("📦 pip install -r requirements.txt ...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
        cwd=tmpdir, capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        log(f"  ⚠️  pip warning: {r.stderr[:300]}")


def _install_node_deps(tmpdir: Path, log):
    if not (tmpdir / "package.json").exists():
        return
    if not shutil.which("node"):
        log("  ⚠️  node not found, skipping npm install")
        return
    log("📦 npm install ...")
    r = subprocess.run(
        ["npm", "install", "--silent"],
        cwd=tmpdir, capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        log(f"  ⚠️  npm warning: {r.stderr[:300]}")


def _run_python(idea: dict, tmpdir: Path, log) -> tuple[bool, str, str]:
    _install_python_deps(tmpdir, log)
    if idea["project_type"] == "web":
        return _check_web_start(idea, tmpdir, log, [sys.executable, idea["entry_point"]])
    log(f"🏃 {idea['run_command']}")
    r = subprocess.run(
        [sys.executable, idea["entry_point"]],
        cwd=tmpdir, capture_output=True, text=True, timeout=30,
    )
    ok = r.returncode == 0
    log(f"{'✅' if ok else '❌'} exit {r.returncode}")
    return ok, r.stdout, r.stderr


def _run_node(idea: dict, tmpdir: Path, log) -> tuple[bool, str, str]:
    if not shutil.which("node"):
        return False, "", "node not found in PATH"
    _install_node_deps(tmpdir, log)
    if idea["project_type"] == "web":
        return _check_web_start(idea, tmpdir, log, ["node", idea["entry_point"]])
    log(f"🏃 {idea['run_command']}")
    r = subprocess.run(
        ["node", idea["entry_point"]],
        cwd=tmpdir, capture_output=True, text=True, timeout=30,
    )
    ok = r.returncode == 0
    log(f"{'✅' if ok else '❌'} exit {r.returncode}")
    return ok, r.stdout, r.stderr


def _check_web_start(idea: dict, tmpdir: Path, log, cmd: list) -> tuple[bool, str, str]:
    port = idea.get("web_port") or 5000
    log(f"🌐 Starting web server (port {port})...")
    proc = subprocess.Popen(
        cmd, cwd=tmpdir,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    for _ in range(20):
        time.sleep(0.75)
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                log(f"✅ Server is up on :{port}")
                # Leave it running — screenshotter will kill it
                return True, f"Server running on :{port}", ""
    proc.kill()
    stdout, stderr = proc.communicate(timeout=5)
    log(f"❌ Server did not start: {stderr[:200]}")
    return False, stdout, stderr
