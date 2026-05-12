import json
import anthropic
from app.config import get_settings
from app.database import get_recent_titles

CLAUDE_MODEL = "claude-sonnet-4-6"


def generate_idea(log) -> dict:
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    recent = get_recent_titles(30)
    avoid_block = "\n".join(f"- {t}" for t in recent) if recent else "None yet"

    prompt = f"""You are a creative software project generator. Invent a unique, fun, visually impressive programming project.

Already built — avoid similar ideas:
{avoid_block}

Requirements:
- Genuinely interesting and impressive when seen on GitHub
- Completable in ~150-250 lines of code total
- Must produce visible output: web UI, rich terminal output, or a saved image
- Language: Python OR JavaScript (pick whichever fits best)
- Lean toward creative / unusual / delightful over boring utilities

Critical rules for entry_point:
- Python web: entry_point must be a .py file that starts a Flask/FastAPI server
- JavaScript web: entry_point must be a .js file (e.g. server.js) using Express — NEVER index.html
- CLI / data_viz: entry_point is the main script file

Respond with ONLY a JSON object, no markdown fences:
{{
  "title": "CoolProjectName",
  "description": "2-3 sentences on what it does and why it is cool",
  "language": "python",
  "project_type": "web | cli | data_viz",
  "tech_stack": ["lib1", "lib2"],
  "entry_point": "server.js",
  "run_command": "node server.js",
  "web_port": 3000
}}

Set web_port to null if project_type is not web."""

    log("🧠 Claude is dreaming up a project idea...")
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip().rstrip("```").strip()

    idea = json.loads(raw)
    log(f"💡 Idea: \"{idea['title']}\" ({idea['language']}, {idea['project_type']})")
    return idea
