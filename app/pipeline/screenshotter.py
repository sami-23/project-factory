import subprocess
import sys
import socket
import time
from html import escape
from pathlib import Path


async def take_screenshot(
    idea: dict,
    tmpdir: Path,
    test_stdout: str,
    output_path: Path,
    log,
) -> bool:
    ptype = idea["project_type"]
    if ptype == "web":
        return await _shot_web(idea, tmpdir, output_path, log)
    elif ptype == "data_viz":
        return _grab_data_viz(tmpdir, output_path, log)
    else:
        return await _shot_terminal(idea, test_stdout, output_path, log)


# ── web ──────────────────────────────────────────────────────────────────────

async def _shot_web(idea: dict, tmpdir: Path, out: Path, log) -> bool:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log("⚠️  Playwright not installed — skipping screenshot")
        return False

    port = idea.get("web_port") or 5000
    lang = idea["language"]
    cmd = [sys.executable, idea["entry_point"]] if lang == "python" else ["node", idea["entry_point"]]

    proc = subprocess.Popen(
        cmd, cwd=tmpdir,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Wait for server
    for _ in range(20):
        time.sleep(0.75)
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=["--no-sandbox"])
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            await page.goto(f"http://localhost:{port}", timeout=15000,
                            wait_until="networkidle")
            # Extra wait for canvas/WebGL/animation frames to render
            has_canvas = await page.query_selector("canvas") is not None
            await page.wait_for_timeout(5000 if has_canvas else 2500)
            await page.screenshot(path=str(out))
            await browser.close()
        log("📸 Web screenshot saved")
        return True
    except Exception as e:
        log(f"⚠️  Web screenshot failed: {e}")
        return False
    finally:
        proc.kill()


# ── data viz ─────────────────────────────────────────────────────────────────

def _grab_data_viz(tmpdir: Path, out: Path, log) -> bool:
    import shutil
    for pattern in ("output.png", "*.png", "*.jpg", "*.svg"):
        found = sorted(tmpdir.glob(pattern))
        if found:
            shutil.copy(found[0], out)
            log(f"📸 Data viz image captured: {found[0].name}")
            return True
    log("⚠️  No image output found for data_viz project")
    return False


# ── terminal ─────────────────────────────────────────────────────────────────

async def _shot_terminal(idea: dict, stdout: str, out: Path, log) -> bool:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log("⚠️  Playwright not installed — skipping screenshot")
        return False

    content = (stdout or "No output captured.").strip()[:3000]
    html = _terminal_html(idea["title"], idea.get("run_command", ""), content)

    tmp_html = out.parent / f"_terminal_{out.stem}.html"
    tmp_html.write_text(html, encoding="utf-8")

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            page = await browser.new_page(viewport={"width": 920, "height": 560})
            await page.goto(tmp_html.as_uri())
            await page.wait_for_timeout(400)
            await page.screenshot(path=str(out))
            await browser.close()
        tmp_html.unlink(missing_ok=True)
        log("📸 Terminal screenshot saved")
        return True
    except Exception as e:
        log(f"⚠️  Terminal screenshot failed: {e}")
        return False


def _terminal_html(title: str, cmd: str, output: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;display:flex;justify-content:center;
     align-items:center;min-height:100vh;padding:32px;
     font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:12px;
       overflow:hidden;width:100%;max-width:860px;
       box-shadow:0 16px 48px rgba(0,0,0,.6)}}
.bar{{background:#21262d;padding:12px 18px;display:flex;
      align-items:center;gap:10px;border-bottom:1px solid #30363d}}
.dots{{display:flex;gap:6px}}
.dot{{width:12px;height:12px;border-radius:50%}}
.r{{background:#ff5f57}}.y{{background:#febc2e}}.g{{background:#28c840}}
.name{{color:#8b949e;font-size:12px;font-weight:600;margin-left:6px}}
.term{{background:#0d1117;padding:22px 24px;font-family:'Courier New',
       monospace;font-size:13px;line-height:1.7;color:#e6edf3;
       min-height:300px;max-height:460px;overflow:hidden}}
.prompt{{color:#79c0ff;margin-bottom:10px}}
.out{{white-space:pre-wrap;word-break:break-all;color:#e6edf3}}
</style></head>
<body>
<div class="card">
  <div class="bar">
    <div class="dots">
      <div class="dot r"></div><div class="dot y"></div><div class="dot g"></div>
    </div>
    <div class="name">{escape(title)}</div>
  </div>
  <div class="term">
    <div class="prompt">$ {escape(cmd)}</div>
    <div class="out">{escape(output)}</div>
  </div>
</div>
</body></html>"""
