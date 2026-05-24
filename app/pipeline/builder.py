import re
import anthropic
from app.config import get_settings

OPUS_MODEL   = "claude-opus-4-7"
REVIEW_MODEL = "claude-sonnet-4-6"

_WEB_UI_RULES = """
CRITICAL — Web UI design quality (this is non-negotiable):
- NEVER use a plain white or light-gray background. Use a DARK theme or a bold, vibrant color scheme.
- CSS custom properties are required: define --bg, --surface, --accent, --text, --muted at :root
- Use a CSS framework via CDN for rapid polish — pick ONE:
    Bootstrap 5 dark:  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
                       <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
                       Then set <html data-bs-theme="dark"> on the html element.
    Tailwind CSS CDN:  <script src="https://cdn.tailwindcss.com"></script>  (add darkMode:'class' config)
- Additionally load a clean font:
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    body { font-family: 'Inter', sans-serif; }
- Structure every page with: a sticky header/navbar with the app name and nav links, a main content area, proper footer
- Use card components with rounded corners (border-radius >= 8px), subtle shadows, and hover lift (transform: translateY(-2px))
- All interactive elements must have visible hover states and smooth transitions (transition: all 0.2s ease)
- Gradient accents are encouraged: use linear-gradient() on headers, hero sections, or key buttons
- Include at least one icon set via CDN, e.g. Bootstrap Icons:
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
- The result must look like a real SaaS product or portfolio piece — NOT a university assignment
"""

_LANG_HINTS = {
    "python": (
        "Use only stdlib + well-known pip packages that ship pre-built wheels "
        "(flask, fastapi, uvicorn, requests, rich, pandas, numpy, matplotlib, "
        "pillow, pydantic, jinja2, etc.). "
        "NEVER use packages that require compilation from source or system-level "
        "build tools (e.g. no obscure C-extension packages, no packages that fail "
        "with 'Getting requirements to build wheel'). "
        "Always include a requirements.txt listing every third-party package. "
        "CRITICAL for Flask/web: NEVER call render_template('x.html') unless you also generate "
        "that template file (e.g. templates/x.html). "
        "Prefer render_template_string(\"\"\"<html>...</html>\"\"\") to keep HTML inline and avoid "
        "TemplateNotFound errors at runtime."
    ),
    "javascript": (
        "Use only well-known npm packages. "
        "Always include package.json with all deps and a 'start' script."
    ),
}


def generate_code(idea: dict, log, prefs: dict = None, plan: str = "") -> list[tuple[str, str]]:
    prefs  = prefs or {}
    manual = prefs.get("manual", False)
    settings = get_settings()
    claude = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=300.0)

    lang = idea["language"]
    web_line = f"Web port: {idea['web_port']}" if idea.get("web_port") else ""

    if manual:
        size_rules = (
            "- Split into 6-10 files with strict separation of concerns\n"
            "- Total code 1500-2500 lines — full, production-quality implementation\n"
            "- For web: multiple pages/views with client-side fetch calls to a JSON API;\n"
            "  polished responsive CSS; real data models with CRUD or search operations\n"
            "- Include meaningful algorithms, data processing, or game/simulation logic\n"
            "- Every file should be substantial — no thin wrappers"
        )
    else:
        size_rules = (
            "- Split into 4-6 files with clear separation of concerns (server, routes, helpers, data, frontend)\n"
            "- Total code 600-1200 lines — make it real, not a toy\n"
            "- For web: build a proper multi-page or multi-section UI with navigation, not a single static page"
        )

    plan_section = f"\n\n## Architecture Blueprint\nFollow this spec exactly:\n\n{plan}" if plan else ""
    web_ui_section = _WEB_UI_RULES if idea.get("project_type") == "web" else ""
    max_tokens = 32000

    gen_prompt = f"""You are an expert software engineer. Generate a complete, fully-featured implementation of this project.
{plan_section}

Project details:
Title: {idea['title']}
Description: {idea['description']}
Language: {lang}
Type: {idea['project_type']}
Tech stack: {', '.join(idea['tech_stack'])}
Entry point: {idea['entry_point']}
Run command: {idea['run_command']}
{web_line}

{_LANG_HINTS.get(lang, '')}
{web_ui_section}
Implementation rules:
- Write COMPLETE, RUNNABLE code — no TODO stubs, no placeholders, no "add your logic here"
{size_rules}
- Use Markdown code blocks with filename on the opening fence: ```python filename.py
- Generate ALL necessary files (source + config + deps file)
- Every interactive feature in the blueprint MUST be fully implemented — partial features are failures
- For web: serve on the specified port, include hardcoded sample/demo data so it works immediately
- CRITICAL for web: every HTML/CSS/JS file the server references MUST be in your output
  - NEVER reference public/index.html, templates/index.html, or any static file unless you include it
  - Every file the server reads from disk must be generated
  - Keep all HTML inline in the server (res.send / render_template_string) to avoid missing file errors
- CRITICAL for Python/Flask: if you call render_template('x.html'), you MUST generate templates/x.html
  - Prefer render_template_string(\"\"\"...\"\"\") to keep HTML inline — avoids TemplateNotFound
  - NEVER call render_template() for a file you do not generate
- For cli: produce colourful, multi-section terminal output with real logic
- For data_viz: save the final image to output.png
- Only output code blocks, nothing else"""

    log(f"⚡ Claude Opus generating code {'(large build)' if manual else ''}...")
    gen_resp = claude.messages.create(
        model=OPUS_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": gen_prompt}],
    )
    raw = gen_resp.content[0].text.strip()
    first_fence = re.search(r"```[^\n]*", raw)
    if first_fence:
        log(f"  🔎 first fence: {first_fence.group(0)[:80]}")
    files = _parse_blocks(raw)
    log(f"📦 Opus produced {len(files)} file(s): {', '.join(f[0] for f in files)}")

    # Claude Sonnet review pass
    file_str = "\n\n".join(f"### {n}\n```\n{c}\n```" for n, c in files)
    review_prompt = f"""Review this code for "{idea['title']}". Fix bugs, missing imports, and anything that would prevent it from running.

Run command: {idea['run_command']}
Type: {idea['project_type']}

{file_str}

Critical checks for web projects:
- Does the server reference any file on disk (sendFile, express.static, readFileSync, render_template, etc.)?
  If yes, that file MUST be in the file list. If it is missing, either add it or rewrite the server to inline the HTML.
- A missing file (ENOENT or TemplateNotFound) causes errors — treat it as a critical bug.

UI quality check (web projects only):
- Does any HTML page have a plain white or light-gray body background (#fff, white, #f0f0f0, etc.)?
  If yes, REPLACE it with a dark theme using CSS variables (--bg: #0d1117 or similar dark color).
- Is Bootstrap 5 CDN or Tailwind CDN included? If not, ADD the Bootstrap 5 dark CDN link and set <html data-bs-theme="dark">.
- Is a Google Fonts Inter/Roboto/Poppins link present? If not, add one and apply to body.
- Does the page have a <nav> or sticky header with the app name? If not, add a minimal one.
- Are there hover states + transitions on buttons and cards? If not, add them.
- The app should look like a polished SaaS product. If it looks like a bare HTML form, upgrade the styling.

Critical checks for Flask/Python web projects:
- Scan every route for render_template('x.html') calls. For EACH call, check the file list for templates/x.html.
  If that template is missing from the file list, you MUST either:
  a) Add the full templates/x.html file to your output, OR
  b) Rewrite the route to use render_template_string(\"\"\"<html>...</html>\"\"\") instead.
  This is the #1 cause of HTTP 500 errors — a TemplateNotFound crash. Do not skip this check.
- Flask must be initialised with an explicit absolute template folder:
    import os
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'),
                          static_folder=os.path.join(BASE_DIR, 'static'))
- If routes are in a Blueprint, the Blueprint must NOT set its own template_folder.

Return ALL files in the same code-block format:
```lang filename
code
```

If everything is correct, return the files unchanged. Only output code blocks."""

    log("🔍 Claude Sonnet reviewing and fixing...")
    review_resp = claude.messages.create(
        model=REVIEW_MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": review_prompt}],
    )
    reviewed = _parse_blocks(review_resp.content[0].text.strip())
    if reviewed:
        files = reviewed
        log(f"✅ Sonnet finalised {len(files)} file(s)")
    else:
        log("⚠️  Review returned nothing — using Opus output as-is")

    # Sanity check: warn on missing render_template targets
    file_names = {f[0] for f in files}
    for fname, code in files:
        for m in re.finditer(r"render_template\(['\"]([^'\"]+)['\"]", code):
            tpl = m.group(1)
            tpl_path = f"templates/{tpl}" if "/" not in tpl else tpl
            if tpl_path not in file_names and tpl not in file_names:
                log(f"⚠️  render_template('{tpl}') in {fname} but '{tpl_path}' not in file list")

    return files


def _parse_blocks(markdown: str) -> list[tuple[str, str]]:
    # Handles: ```lang name.py  OR  ```lang filename=name.py
    pattern = r"```(?:[\w+-]+)?\s+(?:filename=)?([^\n`]+)\n(.*?)```"
    matches = re.findall(pattern, markdown, re.DOTALL)
    if not matches:
        fallback = re.findall(r"```(?:[\w+-]*)\n(.*?)```", markdown, re.DOTALL)
        if fallback:
            return [("main.py", fallback[0].strip())]
    return [(_clean_filename(n), c.strip()) for n, c in matches]


def _clean_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r"^<!--\s*|\s*-->$", "", name)        # <!-- file.html -->
    name = re.sub(r"^/\*\s*|\s*\*/$", "", name)         # /* file.js */
    name = re.sub(r"^//\s*", "", name)                   # // file.js
    name = re.sub(r"^#\s*", "", name)                    # # file.py
    name = re.sub(r"^filename=", "", name, flags=re.IGNORECASE)  # filename=server.js
    name = re.sub(r"[^\w./_-]", "", name)
    return name.strip()
