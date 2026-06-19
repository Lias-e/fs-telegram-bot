# Implementation Plan

## Phase 1 – Project Scaffolding ✅

- [x] **1.1 Create directory structure**
  ```
  src/
  config/
  data/
  logs/
  tests/
  ```
- [x] **1.2 Write `requirements.txt`**
  - `playwright`, `lxml`, `httpx`, `apscheduler`, `pyyaml`, `python-dotenv`, `tenacity`
- [x] **1.3 Write `.env.example`**
  - `TELEGRAM_BOT_TOKEN=`, `TELEGRAM_CHANNEL_ID=`, `TARGET_URL=`, `LOG_LEVEL=`, `POLL_INTERVAL=`
- [x] **1.4 Write `config/settings.yaml`**
  - Default poll interval, retry counts, backoff base, user-agent strings, heartbeat interval
- [x] **1.5 Write `config/selectors.json`**
  - Site-specific CSS selectors for notice container, title, link, date
  - Include a `_meta.validated` field (initially `false`)

## Phase 2 – Core Modules ✅

- [x] **2.1 `src/config.py`**
  - Load `settings.yaml` via `pyyaml`
  - Overlay with environment variables (env wins)
  - Load & return `selectors.json`
  - Validate required env vars at startup (fail fast)
- [x] **2.2 `src/database.py`**
  - `init_db()` – create `notices` table with schema
  - `insert_notice(id, url, title, hash)` – INSERT OR IGNORE
  - `is_duplicate(hash)` – boolean check
  - `get_recent(count)` – for heartbeat summary
  - `backup()` – daily backups with retention pruning
- [x] **2.3 `src/utils.py`**
  - `sha256_hash(content)` – returns hex digest
  - `split_text(text, max_length=4000)` – splits long messages for Telegram
  - `format_notice(title, url, date)` – builds message string
- [x] **2.4 `src/scraper.py`**
  - `fetch_page(url)` – Playwright with random user-agent + 2–5s delay
  - `parse_notices(html, selectors)` – lxml extraction
  - `scrape()` – orchestrate fetch + parse; return list of notices
- [x] **2.5 `src/broadcaster.py`**
  - `send(text)` – POST via httpx with tenacity retry (3 attempts, exp backoff)
  - Handles 4000-char limit via `split_text()`
  - `send_notice(title, url, date)` – format + broadcast
- [x] **2.6 `src/heartbeat.py`**
  - `send()` – reports uptime, total notices, last 3 items
- [x] **2.7 `src/main.py`**
  - `main()` – init db, browser, config, start APScheduler
  - Adaptive polling via `reschedule_job` (5 min if new notices, else 30)
  - Heartbeat every 6h, DB backup every 24h
  - Selector validation on startup (warns via Telegram if zero results)
  - Graceful shutdown (SIGTERM/SIGINT → close browser + db)

## Phase 3 – Containerization ✅

- [x] **3.1 Write `Dockerfile`**
  - Multi-stage build: builder installs deps + Playwright, final image copies artifacts
  - Non-root `appuser`, chromium cache from builder
- [x] **3.2 Write `docker-compose.yml`**
  - `restart: always`, healthcheck every 6h, volumes for data + logs

## Phase 4 – Hardening & Polish ✅

- [x] **4.1 Logging**
  - Rotating file handler (`logs/app.log`, max 5MB, 3 backups)
  - Structured format
- [x] **4.2 Error handling**
  - Catch-all in poll job (log + continue)
  - Playwright timeout (30s)
  - DB health check method
- [x] **4.3 Adaptive polling**
  - Reschedules job interval based on new notice count
- [x] **4.4 Selector validation**
  - Startup scrape test sends Telegram alert if zero results
- [x] **4.5 DB backup**
  - Daily backup to `data/backup/` with 7-day retention

## Phase 5 – Testing & Verification ✅

- [x] **5.1 Unit tests** (`tests/`)
  - `test_database.py` – init, insert, dedup, get_recent
  - `test_utils.py` – sha256, split_text, format_notice
  - `test_config.py` – settings loading, selectors loading, env helpers
- [ ] **5.2 Integration test**
  - Build container: `docker compose build`
  - Run with real `.env`: `docker compose up -d`
  - Verify logs: `docker compose logs -f`
  - Confirm DB created in `data/`
- [ ] **5.3 Deploy on target server**
  - `docker compose up -d`
  - Monitor for first poll cycle
  - Verify first notice appears in Telegram channel

## Files Created

```
fs-telegram-bot/
├── src/
│   ├── __init__.py
│   ├── main.py              # Entry point – scheduler orchestration
│   ├── scraper.py           # Playwright + lxml page scraper
│   ├── broadcaster.py       # Telegram messaging with tenacity retry
│   ├── database.py          # SQLite operations (init, insert, lookup, backup)
│   ├── config.py            # YAML + env config loader
│   ├── heartbeat.py         # Periodic health-check reporter
│   └── utils.py             # Helpers (text splitting, hashing)
├── config/
│   ├── selectors.json       # CSS selectors for target site
│   └── settings.yaml        # Global application settings
├── tests/
│   ├── __init__.py
│   ├── test_database.py
│   ├── test_utils.py
│   └── test_config.py
├── Dockerfile               # Multi-stage build
├── docker-compose.yml       # Service orchestration
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── .gitignore
├── README.md
└── PLAN.md
```
