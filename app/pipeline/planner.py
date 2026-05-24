import anthropic
from app.config import get_settings

CLAUDE_MODEL = "claude-sonnet-4-6"


def plan_project(idea: dict, log, prefs: dict = None) -> str:
    """Generate a detailed architecture spec before code generation."""
    prefs = prefs or {}
    manual = prefs.get("manual", False)
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=120.0)

    feature_count = "6-8" if manual else "4-5"
    file_count    = "6-10" if manual else "4-6"
    data_rows     = "20-30" if manual else "10-15"

    is_web = idea.get("project_type") == "web"
    api_section = """
## REST API Endpoints (list every route)
For each endpoint: METHOD /path — purpose, key request fields, response shape.
Design a proper REST API with at least 5-6 endpoints covering full CRUD + any domain-specific actions.
""" if is_web else ""

    ui_section = """
## UI Pages / Sections
List every distinct view or section the user sees. For each:
- What data it displays
- What the user can click / type / drag / toggle
- Which API endpoints it calls
Include a sticky header/nav and a footer.
""" if is_web else ""

    prompt = f"""You are a senior software architect. Produce a detailed implementation blueprint for the project below.
This blueprint will be handed directly to a code generator — be precise and concrete, not vague.

Project: {idea['title']}
Description: {idea['description']}
Language: {idea['language']}
Type: {idea['project_type']}
Tech stack: {', '.join(idea['tech_stack'])}
Entry point: {idea['entry_point']}
Run command: {idea['run_command']}

---

## File Structure ({file_count} files)
List every file to generate. For each: filename — one-sentence description of its exact contents.
Example:
- server.py — Flask app: registers blueprints, configures CORS, serves on PORT env var
- routes/api.py — REST endpoints for items (CRUD) and stats
- templates/index.html — Single-page app shell; loads app.js and styles.css
- static/app.js — Vanilla JS: fetches API, renders table, handles modals
- static/styles.css — Dark-theme CSS with CSS variables, card + table styles
- data.py — In-memory store with {data_rows} hardcoded sample records and helper functions
{api_section}{ui_section}
## Data Models
Define every entity: class/dict name, all fields with types, example values.
Include {data_rows} realistic hardcoded sample records (not "sample1", "sample2" — use real names/values relevant to the domain).

## Interactive Features (implement ALL {feature_count})
Each feature must be specific and self-contained. Bad: "user can filter data". Good: "column header click sorts table ascending/descending with ▲/▼ indicator and current sort highlighted". List exactly {feature_count}:
1.
2.
3.
4.{"5.\\n6." if manual else "5."}

## Key Algorithms / Logic
Describe any non-trivial logic: how state is managed, what computations happen client-side vs server-side, any interesting algorithms relevant to the domain (search, scoring, simulation, generation, etc.).

## Implementation Notes
Tricky parts the coder should watch out for: event delegation, async patterns, edge cases, data transformations, animation timing, etc."""

    log("📐 Claude designing architecture...")
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    plan = resp.content[0].text.strip()
    log(f"📋 Architecture ready — {len(plan.splitlines())} lines, {len(plan)} chars")
    return plan
