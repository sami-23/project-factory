import re
import anthropic
from openai import OpenAI
from app.config import get_settings

GPT_MODEL = "gpt-4o"
CLAUDE_MODEL = "claude-sonnet-4-6"

_LANG_HINTS = {
    "python": (
        "Use only stdlib + well-known pip packages. "
        "Always include a requirements.txt listing every third-party package."
    ),
    "javascript": (
        "Use only well-known npm packages. "
        "Always include package.json with all deps and a 'start' script."
    ),
}


def generate_code(idea: dict, log) -> list[tuple[str, str]]:
    settings = get_settings()
    oai = OpenAI(api_key=settings.openai_api_key)
    claude = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    lang = idea["language"]
    web_line = f"Web port: {idea['web_port']}" if idea.get("web_port") else ""

    gpt_prompt = f"""Generate a complete, working implementation of this project.

Title: {idea['title']}
Description: {idea['description']}
Language: {lang}
Type: {idea['project_type']}
Tech stack: {', '.join(idea['tech_stack'])}
Entry point: {idea['entry_point']}
Run command: {idea['run_command']}
{web_line}

{_LANG_HINTS.get(lang, '')}

Rules:
- Write complete, runnable code — no TODO stubs or placeholders
- Use Markdown code blocks with filename on the opening fence: ```python filename.py
- Generate ALL necessary files (source + deps file)
- For web: serve on the specified port, include hardcoded sample/demo data so it works immediately
- For cli: produce colourful, interesting terminal output
- For data_viz: save the final image to output.png
- Only output code blocks, nothing else"""

    log("⚡ GPT-4o generating code...")
    gpt_resp = oai.chat.completions.create(
        model=GPT_MODEL,
        messages=[{"role": "user", "content": gpt_prompt}],
        max_tokens=8000,
    )
    raw = gpt_resp.choices[0].message.content.strip()
    files = _parse_blocks(raw)
    log(f"📦 GPT produced {len(files)} file(s): {', '.join(f[0] for f in files)}")

    # Claude review pass
    file_str = "\n\n".join(f"### {n}\n```\n{c}\n```" for n, c in files)
    review_prompt = f"""Review this code for "{idea['title']}". Fix any bugs, missing imports, or issues that would prevent it from running.

Run command: {idea['run_command']}
Type: {idea['project_type']}

{file_str}

Return ALL files in the same code-block format:
```lang filename
code
```

If everything is correct, return the files unchanged. Only output code blocks."""

    log("🔍 Claude reviewing and fixing code...")
    review_resp = claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": review_prompt}],
    )
    reviewed = _parse_blocks(review_resp.content[0].text.strip())
    if reviewed:
        files = reviewed
        log(f"✅ Claude finalised {len(files)} file(s)")
    else:
        log("⚠️  Claude review returned nothing — using GPT output as-is")

    return files


def _parse_blocks(markdown: str) -> list[tuple[str, str]]:
    pattern = r"```(?:\w+)?\s+([^\n`]+)\n(.*?)```"
    matches = re.findall(pattern, markdown, re.DOTALL)
    if not matches:
        fallback = re.findall(r"```(?:[\w+-]*)\n(.*?)```", markdown, re.DOTALL)
        if fallback:
            return [("main.py", fallback[0].strip())]
    return [(_clean_filename(n), c.strip()) for n, c in matches]


def _clean_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r"^<!--\s*|\s*-->$", "", name)   # <!-- file.html -->
    name = re.sub(r"^/\*\s*|\s*\*/$", "", name)    # /* file.js */
    name = re.sub(r"^//\s*", "", name)              # // file.js
    name = re.sub(r"^#\s*", "", name)               # # file.py
    return name.strip()
