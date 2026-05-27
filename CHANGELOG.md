## v2.0.0 — Max-token resilience + port reliability + blueprint viewer (2026-05-25)

### New features
- **Architecture Blueprint viewer**: the Sonnet planning doc is now saved to the DB (`plan_text` column) and exposed via `GET /runs/{id}/plan`; a **Blueprint** button appears on every card and list row that has a saved plan; clicking it opens a styled modal that renders the markdown (section headers, bullets, inline code, bold) in the dark theme
- **Max-token continuation loop**: when Opus hits its output ceiling mid-generation, the pipeline automatically sends a multi-turn continuation request ("continue exactly where you left off") and repeats up to 5 times until the response completes naturally; the loop accumulates cost correctly across all rounds
- **Port injection + stale-process cleanup** in `tester.py`: `_kill_port(port)` kills any process already holding the target port before each server start (Windows: `netstat -ano` + `taskkill`; Linux/Mac: `fuser -k`); `PORT=<web_port>` is injected into the subprocess environment so servers that check `process.env.PORT` always bind to the correct port

### Changes
- `builder.py`: per-size `gen_tokens` / `review_tokens` removed from `_SIZE_CONFIG` — output volume is controlled by the prompt's `size_rules`, not a token budget; `_OPUS_MAX_TOKENS = 32_000` and `_SONNET_MAX_TOKENS = 16_000` constants used for every API call; JavaScript lang hint now requires `const PORT = parseInt(process.env.PORT) || <fallback>` pattern
- `database.py`: `plan_text TEXT` column added + auto-migration on startup
- `orchestrator.py`: `db.update_run(run_id, plan_text=plan)` called immediately after planning step
- `main.py`: `GET /runs/{run_id}/plan` endpoint added; `has_plan` flag computed per run in dashboard route
- `index.html`: Blueprint button in grid and list views; plan modal with minimal markdown-to-HTML renderer (`_mdToHtml`); `closePlanModal()` wired to Escape key

---

## v1.9.0 — Project size selector + estimated build cost (2026-05-25)

### New features
- **Project Size selector** in Build Now modal: Minimal / Standard / Large
  - Minimal: 200–400 lines, 2–4 files, 3 features — fast & cheap (auto daily builds use this)
  - Standard: 600–1200 lines, 4–7 files, 5–6 features (default for manual builds)
  - Large: 1500–2500 lines, 7–10 files, 7–9 features — full production build
- **Dynamic timeouts** scale with size: planner 90/120/180s; generation 300/600/1200s; Anthropic HTTP client timeout 120/300/480s
- **Estimated build cost** tracked per-run from Anthropic usage tokens:
  - Opus 4.7 generation: $15/MTok in + $75/MTok out
  - Sonnet 4.6 (planner + review): $3/MTok in + $15/MTok out
  - Costs logged during build and stored as `cost_usd` in DB
  - Shown as `~$X.XXX` green badge on every card and list row
- **Size badge** (blue) on cards showing which tier was used
- **Auto builds are always Minimal** — scheduler injects `size: "minimal"` when prefs are absent; manual Build Now defaults to Standard

### Changes
- `planner.py`: `manual` bool replaced with `size` tier; returns `(plan, cost)` tuple
- `builder.py`: `_SIZE_CONFIG` dict drives lines/files/features/token budgets/timeouts per tier; returns `(files, cost)` tuple; removed `manual` bool
- `orchestrator.py`: `_PLAN_TIMEOUTS` / `_GEN_TIMEOUTS` dicts; auto-injects `size: "minimal"` for scheduled runs; unpacks costs from planner + builder; saves `build_size` + `cost_usd` to DB
- `database.py`: `build_size TEXT` and `cost_usd REAL` columns added + migrations
- `index.html`: Size dropdown in Build Now modal; `size` sent in prefs (replaces `manual: true`); size + cost badges on grid cards and list rows

---

## v1.8.0 — Three-stage pipeline: Plan → Opus → Review (2026-05-24)

### New pipeline
The code-generation stage is now three distinct steps:

**Step 1 — Architecture planning** (`planner.py`, Claude Sonnet):
Produces a detailed technical spec before any code is written:
- Exact file list with roles
- Full REST API endpoint definitions
- Data models with 10–30 realistic hardcoded sample records
- UI sections with interaction descriptions
- 4–8 named, concrete interactive features (vague features rejected)
- Key algorithms and implementation notes

**Step 2 — Code generation** (`builder.py`, Claude Opus 4.7):
Implements the full spec with a 32k-token budget — replaced GPT-4o entirely.
Opus follows complex multi-file instructions far more reliably and produces genuinely feature-rich output.

**Step 3 — Review** (`builder.py`, Claude Sonnet 4.6):
Bug-fix pass: missing imports, TemplateNotFound, white backgrounds, missing UI polish.

### Changes
- `planner.py` added — new pipeline stage between ideation and code generation
- `builder.py` rewritten: GPT-4o removed, Claude Opus 4.7 is the code generator; Sonnet remains reviewer
- `orchestrator.py`: plan step inserted between ideation and generation; generation timeout raised to 600s
- `requirements.txt`: `openai` and `httpx` pin removed (no longer needed)
- `config.py`: `openai_api_key` field removed
- Code size targets raised: 600–1200 lines (auto), 1500–2500 lines (manual)

### Why Opus over GPT-4o
GPT-4o would produce single-feature demos regardless of prompt length. Claude Opus 4.7 has superior instruction-following for complex multi-file specs and consistently implements every named feature in the blueprint.

---

## v1.7.0 — Modern UI enforcement for generated projects (2026-05-23)

### New features
- **Dark-theme requirement**: all generated web projects must now use a dark or vibrant color scheme — plain white/gray backgrounds are banned in the prompt
- **Bootstrap 5 dark CDN** (or Tailwind) required in every generated web page; `<html data-bs-theme="dark">` enforced
- **Google Fonts Inter** injected via CDN link + applied to `body` in every generated web project
- **Bootstrap Icons CDN** added for visual richness
- **Sticky header/navbar** with app name required in all generated web UIs
- **Card layouts** with rounded corners, box-shadow, and hover-lift (`translateY(-2px)`) enforced
- **Smooth transitions** (`transition: all 0.2s ease`) required on all interactive elements
- **Gradient accents** encouraged on hero sections and primary buttons
- **CSS custom properties** (`--bg`, `--surface`, `--accent`, `--text`, `--muted`) required at `:root`
- Claude review pass now runs a dedicated **UI quality check**: detects white backgrounds, missing frameworks, missing fonts/nav/hover states, and fixes them before the project is tested

### How it works
`_WEB_UI_RULES` constant injected into the GPT generation prompt for all `project_type == "web"` ideas. Claude's review pass applies a second verification layer and upgrades any styling that GPT skipped. Two-pass enforcement means projects that get past one check are caught by the other.

---

## v1.6.0 — Dashboard UI overhaul + category tracking (2026-05-23)

### New features
- **Search**: live search bar filters by title, description, and tech-stack libs simultaneously
- **Filters**: dropdowns for Language, Project Type, Status, and Category — all stackable
- **List view**: toggle between card grid (⊞) and compact list (≡) layouts; result count shown in toolbar
- **Clickable tags**: language/type/category badges on cards set the matching filter; tech-stack tags go into the search box
- **Category stored in DB**: ideator now returns `category` in idea JSON (e.g. "Mini game", "Science / math"); persisted alongside `tech_stack` in new DB columns; auto-migrated on startup for existing databases
- **Escape key** closes any open modal

### Fixes
- Unified action-button style (Logs, GitHub, ZIP, Retry, Delete) — consistent hover colours
- Header now shows running-indicator pulse next to Build Now button while a build is in progress

---

## v1.5.0 — ZIP download + manual build mode (2026-05-18)

### New features
- **ZIP download**: generated project files are persisted to `data/projects/{run_id}/` after code generation; `GET /runs/{id}/download` zips the project dir + screenshot and returns `{title}.zip`; green ↓ ZIP button on cards where files exist
- **Manual build mode**: Build Now always opens an options modal (Language, Category, Project Type); manual builds request 1000–2000 lines across 6–10 files vs 400–800 for scheduled auto-builds; `manual: true` pref flag drives both ideator and builder scope branches
- **Retry failed runs**: `POST /runs/{id}/retry` reloads `idea_json` and re-runs the pipeline with the same idea
- **Delete runs**: `DELETE /runs/{id}` removes DB row, screenshot file, and persisted project directory
- **Descriptive GitHub commit messages**: each pushed file now carries a commit message with project title, description, language, type, and tech stack instead of "Initial commit"

### Fixes
- `render_template` completeness check: both GPT prompt and Claude review prompt now enforce that every `render_template('x.html')` call has a matching template file; post-review sanity log warns if still missing
- `_clean_filename` strips `filename=` prefix case-insensitively; `_parse_blocks` regex also handles `filename=` in the fence header
- Entry-point mismatch resolver: if the declared `entry_point` is missing from generated files, orchestrator scans for the closest name match and patches `idea["entry_point"]` before testing
- 12-category rotation list in ideator with explicit ban on particle/space/canvas animations to improve project diversity
- Code size targets increased to 400–800 lines (auto) / 1000–2000 lines (manual), token budget doubled to 16 000

---

## v1.4.0 — SSE stability + version display (2026-05-15)

### New features
- **Version badge** in header: `git:<sha>` read via `git rev-parse --short HEAD`; falls back to a `VERSION` file walk for Railway deployments where git is absent
- **Heartbeat comments** in SSE stream every 15 s to prevent Railway/nginx proxy from closing idle connections
- `cleanup_stuck_runs()` called on startup — any run left in `running` state after a crash/restart is marked `failed` so the SSE loop doesn't spin forever

### Fixes
- SSE stream driven by the in-process `is_running()` flag rather than DB status; `sent` counter tracks already-emitted lines so they are never replayed after reconnect
- `db.get_last_run()` added to drain final log lines after the pipeline finishes before sending `__done__`
- `X-Accel-Buffering: no` header added to SSE response to prevent nginx from buffering lines

---

## v1.3.0 — GitHub push reliability + screenshot fixes (2026-05-12)

### New features
- **Playwright screenshots**: `wait_until="networkidle"` + canvas/WebGL detection + 5 000 ms extra wait to avoid all-black screenshots for WebGL projects

### Fixes
- Replaced GitHub Data API push with plain `git` CLI subprocess (`init / add / commit / push`) — Data API returns 409 on empty repos
- GitHub repo is only created *after* the project passes testing; empty repos on failure eliminated
- Node.js entry-point guard: if `entry_point` is an HTML file, tester falls back to `npx serve` instead of passing it to `node`
- Flask absolute template-folder pattern enforced in Claude review prompt: `BASE_DIR = os.path.dirname(os.path.abspath(__file__))`; `Flask(__name__, template_folder=…)`

---

## v1.2.0 — Two-AI pipeline + async SSE (2026-05-10)

### New features
- **Two-AI collaboration**: GPT-4o generates bulk code (volume + breadth); Claude Sonnet reviews, fixes bugs, and enforces quality constraints
- All blocking pipeline steps wrapped in `asyncio.wait_for(asyncio.to_thread(…))` so the event loop stays free for SSE streaming while code generation, testing, and git pushes run
- `idea_json` stored in DB for retry support

### Fixes
- Live log no longer freezes at "Server is up": `time.sleep()` polling in tester moved off the event loop
- Python `_LANG_HINTS` explicitly bans packages requiring C-extension compilation (`pip wheel` failures)
- `_clean_filename` strips HTML/JS/Python comment wrappers around filenames in GPT code fences
- CLI failures now log stderr (500 chars) and stdout (300 chars) for diagnosis

---

## v1.1.0 — Railway deployment (2026-05-08)

### New features
- `Dockerfile` based on `python:3.12-bookworm` (not slim) for Playwright font-package compatibility
- Shell-form `CMD` with `${PORT:-8000}` — `startCommand` removed from `railway.toml` so Railway shell-expands `$PORT` correctly
- APScheduler (asyncio mode) daily cron trigger; scheduler started/stopped in FastAPI lifespan events
- SQLite via stdlib `sqlite3`; Volume mounted at `/data` in Railway

### Fixes
- `httpx<0.28.0` pin to resolve `proxies` TypeError with `openai==1.57.0`
- `$PORT` was being passed as a literal string when set via `startCommand` — fixed by removing it

---

## v1.0.0 — Initial build (2026-05-07)

- FastAPI + Uvicorn web server with Jinja2 dashboard
- Daily pipeline: Claude ideates → GPT-4o generates code → subprocess test → Playwright screenshot → PyGithub repo → Anthropic README writer → git push
- Server-Sent Events live log stream
- Build history with status badges and screenshots
