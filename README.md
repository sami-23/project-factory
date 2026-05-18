# Project Factory

An autonomous AI pipeline that wakes up daily, invents a software project, builds it, tests it, screenshots it, and publishes it to GitHub — fully unattended. A web dashboard lets you watch builds in real time, browse history, and trigger or retry builds manually.

Built by **Sami Malik** using **Claude** (Anthropic) + **GPT-4o** (OpenAI).

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                        Daily Cron (APScheduler)                 │
│                     or manual "Build Now" click                 │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. IDEATOR  (Claude Sonnet)                                     │
│     • Picks an unused category from a 12-category rotation list │
│     • Returns structured JSON: title, language, type, files…    │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. BUILDER  (GPT-4o → Claude review)                           │
│     • GPT-4o generates all source files (~400-800 lines)        │
│     • Claude reviews for bugs, missing imports, bad paths       │
│     • Returns a list of (filename, code) pairs                  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. TESTER  (subprocess)                                        │
│     • Writes files to a temp directory                          │
│     • pip install / npm install                                 │
│     • Runs the entry point; checks exit code                    │
│     • For web: polls port open + HTTP GET / for non-500         │
│     • On failure: logs stderr, marks run failed, no GitHub repo │
└───────────────────────────────┬─────────────────────────────────┘
                                │  (only if tests pass)
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. SCREENSHOTTER  (Playwright / Chromium)                      │
│     • web     → navigates to localhost, waits for networkidle,  │
│                 extra 5 s if <canvas> detected                  │
│     • cli     → renders stdout as styled terminal HTML,         │
│                 screenshots with Playwright                     │
│     • data_viz → copies first .png/.jpg/.svg from temp dir     │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. PUBLISHER  (PyGithub + git CLI)                             │
│     • Creates a public GitHub repo (handles name collisions)    │
│     • git init / add / commit / push via subprocess             │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  6. README WRITER  (Claude Sonnet)                              │
│     • Writes a polished README.md with features, install steps, │
│       tech table, and screenshot embed                          │
│     • Pushed as a second commit to the repo                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
project-factory/
├── app/
│   ├── main.py               # FastAPI app, routes, SSE stream
│   ├── config.py             # Pydantic settings (env vars)
│   ├── database.py           # SQLite helpers (runs, logs)
│   ├── scheduler.py          # APScheduler daily cron trigger
│   ├── pipeline/
│   │   ├── orchestrator.py   # Async pipeline runner, _running flag
│   │   ├── ideator.py        # Claude: generate project idea JSON
│   │   ├── builder.py        # GPT-4o generate → Claude review
│   │   ├── tester.py         # subprocess: install, run, HTTP check
│   │   ├── screenshotter.py  # Playwright: web / CLI / data_viz
│   │   ├── readme_writer.py  # Claude: write README.md
│   │   └── publisher.py      # PyGithub + git CLI push
│   └── templates/
│       └── index.html        # Dashboard (dark GitHub theme, SSE logs)
├── Dockerfile                # python:3.12-bookworm + Node 20 + Playwright
├── railway.toml              # Railway deploy config
├── requirements.txt
└── VERSION                   # Version string shown in dashboard header
```

---

## Key Design Decisions

### Async + blocking coexistence
The FastAPI event loop must stay free for SSE streaming while the pipeline runs synchronous blocking calls (HTTP, subprocess, `time.sleep`). Every pipeline step is wrapped in `asyncio.to_thread()` inside `asyncio.wait_for()` — so blocking calls run in a thread pool and each step has a hard timeout (default 300 s, 480 s for code generation).

### Two-AI collaboration
- **Claude** handles creativity and quality: ideation, code review, README writing
- **GPT-4o** handles volume: generating 400–800 lines of multi-file code in one shot
- Claude's review pass fixes bugs, enforces Flask `BASE_DIR` template paths, and ensures all static files referenced by the server are actually generated

### SSE live log
The `/logs/stream` endpoint uses Server-Sent Events. The generator loop is driven by the in-memory `is_running()` flag (not DB status), which prevents orphaned `running` rows from looping forever after a restart. A `: heartbeat` SSE comment is sent every 15 s to keep Railway's nginx proxy from closing idle connections.

### Test-before-publish gate
The pipeline creates a GitHub repo **only after** the project passes its tests. For web projects this means: port opens **and** HTTP GET `/` returns a non-5xx response. This prevents empty repos from being created on broken builds.

### Entry-point auto-correction
If GPT declares `entry_point: server.js` but generates `app.js`, the orchestrator scans the generated file list, finds the closest match by name priority, and patches `idea["entry_point"]` before handing off to the tester.

---

## Dashboard Features

- **Live build log** — SSE stream shows logs line-by-line as they arrive
- **Build history** — card grid with screenshot, language/type badges, GitHub link
- **Build Now** — opens an options modal to pin language, category, or project type
- **↺ Retry** — re-runs the exact same idea through the pipeline (only on failed builds)
- **✕ Delete** — removes a failed run from history and deletes its screenshot

---

## Environment Variables

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | GPT-4o code generation |
| `ANTHROPIC_API_KEY` | Claude ideation, review, README |
| `GITHUB_TOKEN` | Personal access token (repo scope) |
| `GITHUB_USERNAME` | GitHub username for repo links |
| `RUN_HOUR` | UTC hour for daily auto-build (default: `9`) |
| `RUN_MINUTE` | Minute offset (default: `0`) |
| `DATA_DIR` | Path for SQLite DB + screenshots (default: `data`) |

---

## Deploying to Railway

1. Fork this repo and connect it to a new Railway project
2. Set all environment variables above in Railway's Variables tab
3. Add a **Volume** mounted at `/data` — this persists the SQLite database and screenshots across deploys
4. Railway builds via `Dockerfile` automatically; the `CMD` uses `${PORT:-8000}` so Railway's dynamic port injection works

The `railway.toml` sets `builder = "DOCKERFILE"` and a `/` healthcheck. No `startCommand` override — the shell-form `CMD` in the Dockerfile handles `$PORT` expansion correctly.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI + Uvicorn |
| Templating | Jinja2 |
| Database | SQLite (via stdlib `sqlite3`) |
| Scheduling | APScheduler (asyncio mode) |
| AI — ideation & review | Anthropic Claude Sonnet (`claude-sonnet-4-6`) |
| AI — code generation | OpenAI GPT-4o |
| GitHub integration | PyGithub + git CLI subprocess |
| Screenshots | Playwright (headless Chromium) |
| Container base | `python:3.12-bookworm` + Node.js 20 |
| Hosting | Railway |
