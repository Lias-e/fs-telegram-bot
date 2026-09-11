# Implementation Plan

Status: **Phases 1–4 done. Phase 6 correctness + runtime fixes implemented in code; verify with tests before deploy.**  
Evidence: [`docs/RESEARCH-ISSUES.md`](docs/RESEARCH-ISSUES.md) — 22 findings (F01–F22) from code + Telegram Bot API + Playwright + Python sqlite3 + live HTML (2026-09-11).

---

## Phase 1 – Project Scaffolding ✅

- [x] **1.1 Create directory structure** (`src/`, `config/`, `data/`, `logs/`, `tests/`)
- [x] **1.2 Write `requirements.txt`**
- [x] **1.3 Write `.env.example`**
- [x] **1.4 Write `config/settings.yaml`**
- [x] **1.5 Write `config/selectors.json`**

## Phase 2 – Core Modules ✅

- [x] **2.1 `src/config.py`**
- [x] **2.2 `src/database.py`**
- [x] **2.3 `src/utils.py`**
- [x] **2.4 `src/scraper.py`** — httpx + lxml (Playwright dropped after static HTML proof)
- [x] **2.5 `src/broadcaster.py`**
- [x] **2.6 `src/heartbeat.py`**
- [x] **2.7 `src/main.py`**
- [x] **2.8 `src/commands.py`**

## Phase 3 – Containerization ✅

- [x] **3.1 `Dockerfile`** — slim Python image, non-root `appuser` (no Chromium)
- [x] **3.2 `docker-compose.yml`** — `init: true`, heartbeat-file healthcheck

## Phase 4 – Hardening & Polish ✅

- [x] **4.1 Rotating file logs**
- [x] **4.2 Catch-all in poll job, DB health check**
- [x] **4.3 Adaptive polling**
- [x] **4.4 Startup selector validation** (ops → admin DM)
- [x] **4.5 Daily DB backup**

## Phase 5 – Testing & Verification

- [x] **5.1 Unit tests** — database, utils, config, scraper fixtures, poll seed/send-order, callbacks
- [ ] **5.2 Integration test** — private test channel after unit suite green
- [ ] **5.3 Deploy on target server** — blocked on 5.2

---

## Phase 6 – Defects

### 6.1 Correctness (must ship)

- [x] **F03 Scrape all `/annonces/` links** — unique links via selectors; fixtures prove ~31 on homepage
- [x] **F01 Send, then record** — `insert_notice` only after successful channel send
- [x] **F02 Seed on empty DB** — insert all current URLs, send nothing
- [x] **F05 HTML parse_mode** — escape titles; no legacy Markdown
- [x] **F06 Short `callback_data`** — `dept|{slug}` ≤ 64 bytes

### 6.2 Runtime / data integrity

- [x] **F08 Serialize SQLite writes** — `threading.Lock`
- [x] **F07 Require `ADMIN_TELEGRAM_ID`**
- [x] **F09 Compose / Chromium** — N/A after dropping Playwright; `init: true` kept
- [x] **F10 Drop unused startup browser** — no Playwright
- [x] **F11 Do not wait for `networkidle`** — N/A (httpx)
- [x] **F14 `deleteWebhook`; ERROR on getUpdates; offset after handle**
- [x] **F12 Heartbeat file healthcheck** — `data/last_poll`
- [x] **F13 Volume ownership** — documented in README
- [x] **F16 Ops to admin DM**
- [x] **F22 Relative DB paths**

### 6.3 Config / docs

- [x] **F21** — removed unused `POLL_INTERVAL`; YAML `retry:` wired into tenacity; dropped unused `content_area` / `seen_at`
- [x] **F19** — README documents URL primary key

### 6.4 Tests

- [x] Fixture HTML parse count
- [x] Seed / first-run
- [x] Send failure → URL unseen
- [x] HTML escape for special titles
- [x] `callback_data` ≤ 64 bytes
- [x] `validate_env` rejects missing admin
- [x] `extract_date` on `02جوان 2025` (optional whitespace)

### 6.5 Optional (not required)

- [ ] F04, F15, F20 — deferred

---

## Phase 7 – Integration and deploy

Only after unit tests for Phase 6 are green.

- [ ] **7.1** `docker compose build && docker compose up -d` against a **private test channel**
- [ ] **7.2** Confirm first cycle seeds with no flood; second cycle with a fixture/new URL sends one message
- [ ] **7.3** Confirm `/subscribe` Computer Science button works
- [ ] **7.4** Confirm Arabic/French titles render
- [ ] **7.5** Production channel: bot is admin, volume `./data` is backed up, then `docker compose up -d`

---

## Files

```
fs-telegram-bot/
├── src/
│   ├── main.py
│   ├── scraper.py
│   ├── broadcaster.py
│   ├── commands.py
│   ├── database.py
│   ├── config.py
│   ├── heartbeat.py
│   └── utils.py
├── config/
│   ├── selectors.json
│   └── settings.yaml
├── tests/
│   ├── fixtures/
│   ├── test_database.py
│   ├── test_utils.py
│   ├── test_config.py
│   ├── test_scraper.py
│   ├── test_poll.py
│   └── test_commands.py
├── docs/
│   └── RESEARCH-ISSUES.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── README.md
└── PLAN.md
```
