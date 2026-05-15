import json
import anthropic
from app.config import get_settings
from app.database import get_recent_titles

CLAUDE_MODEL = "claude-sonnet-4-6"


def generate_idea(log) -> dict:
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=90.0)

    recent = get_recent_titles(30)
    avoid_block = "\n".join(f"- {t}" for t in recent) if recent else "None yet"

    prompt = f"""You are a creative software project generator. Invent a unique, fun programming project.

Already built — avoid similar ideas AND similar categories:
{avoid_block}

Pick ONE category from this list that is NOT represented in the already-built list above.
Rotate through the full list over time — do not cluster in the same area.

Categories (pick the least-used one relative to the list above):
1. Mini game (snake, tetris, minesweeper, breakout, word game, quiz)
2. Music / audio (beat sequencer, chord explorer, waveform visualizer, piano)
3. Data tool (CSV analyzer, JSON formatter, stats dashboard, log parser)
4. Generative art (fractal, L-system, maze, mosaic, pixel art generator) — NOT particles or space
5. Productivity (pomodoro, habit tracker, markdown previewer, note taking)
6. Science / math (cellular automaton, gravity sim, fourier series, sorting visualizer)
7. Finance / numbers (budget tracker, tip calculator, currency converter, compound interest)
8. Language / text (word frequency map, cipher tool, lorem generator, text diff)
9. Geography / maps (ASCII world map, timezone clock, country quiz, distance calculator)
10. Fun / novelty (horoscope generator, excuse generator, compliment bot, emoji art)
11. Developer tool (regex tester, color palette picker, base converter, cron explainer)
12. Retro / nostalgia (ASCII art, old-school terminal animation, BBS-style board)

Requirements:
- Completable in ~150-250 lines of code total
- Must produce visible output: web UI, rich terminal output, or a saved image
- Language: Python OR JavaScript (pick whichever fits best)
- Interesting and delightful — avoid generic "hello world" style projects
- NO particle systems, NO space/galaxy themes, NO generic canvas animations

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
