# Implementation Plan

Status: **Phases 1–4 and unit tests are done. Do not deploy until Phase 6 defects are fixed.**  
Evidence: [`docs/RESEARCH-ISSUES.md`](docs/RESEARCH-ISSUES.md) — 22 findings (F01–F22) from code + Telegram Bot API + Playwright + Python sqlite3 + live HTML (2026-09-11).

---

## Phase 1 – Project Scaffolding ✅

- [x] **1.1 Create directory structure** (`src/`, `config/`, `data/`, `logs/`, `tests/`)
- [x] **1.2 Write `requirements.txt`**
- [x] **1.3 Write `.env.example`**
- [x] **1.4 Write `config/settings.yaml`**
- [x] **1.5 Write `config/selectors.json`**

## Phase 2 – Core Modules ✅ (shipped; several behaviors diverge from this original spec — see Phase 6)

- [x] **2.1 `src/config.py`** — loads YAML/JSON; validates `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHANNEL_ID`
- [x] **2.2 `src/database.py`** — SQLite notices / subscriptions / settings
- [x] **2.3 `src/utils.py`** — hash, split, format, date extract
- [x] **2.4 `src/scraper.py`** — Playwright + lxml
- [x] **2.5 `src/broadcaster.py`** — httpx + tenacity
- [x] **2.6 `src/heartbeat.py`**
- [x] **2.7 `src/main.py`** — scheduler, startup scrape, command thread
- [x] **2.8 `src/commands.py`** — admin getUpdates loop (added after original plan)

## Phase 3 – Containerization ✅ (image builds; compose is missing Playwright’s recommended flags)

- [x] **3.1 `Dockerfile`** — multi-stage, non-root `appuser`
- [x] **3.2 `docker-compose.yml`** — `restart: always`, data/logs volumes

## Phase 4 – Hardening & Polish ✅ (present, not all correct)

- [x] **4.1 Rotating file logs**
- [x] **4.2 Catch-all in poll job, 30s Playwright timeout, DB health check**
- [x] **4.3 Adaptive polling**
- [x] **4.4 Startup selector validation**
- [x] **4.5 Daily DB backup**

## Phase 5 – Testing & Verification

- [x] **5.1 Unit tests** — database, utils, config only
- [ ] **5.2 Integration test** — blocked on Phase 6 (selectors, first-run flood, send-then-record, Markdown, callback_data)
- [ ] **5.3 Deploy on target server** — blocked on 5.2

---

## Phase 6 – Defects to fix before any deploy

Source of each item is cited in `docs/RESEARCH-ISSUES.md`. Do these in order.

### 6.1 Correctness (must ship)

- [ ] **F03 Scrape all `/annonces/` links, not only the carousel** — `notice_container` is `div.item`. Live homepage (2026-09-11): 7 carousel slides vs 31 `/annonces/` links. Newer list-panel IDs (9333, 9330, 9326, …) are invisible. Change selectors (or collect every `a[href*="/annonces/"]` + nearby heading). Re-stamp `selectors.json` `_meta`.
- [ ] **F01 Send, then record** — `insert_notice` runs before `broadcaster.send`. A Telegram 400/5xx permanently drops that URL. Record only after a successful send (or a `sent_at` column).
- [ ] **F02 Seed on empty DB** — if `notices` is empty after a scrape, insert all current URLs and send nothing.
- [ ] **F05 Stop using legacy Markdown on untrusted titles** — `parse_mode: Markdown` with `*{title}*`. Switch to HTML + escape `<`, `>`, `&`, or send plain text.
- [ ] **F06 Fix department `callback_data`** — Telegram allows 1–64 bytes. CS URL with `dept|` is 68 bytes and is expected to 400 the whole keyboard. Use a short id (`dept|info`).

### 6.2 Runtime / data integrity

- [ ] **F08 Serialize SQLite writes** — `check_same_thread=False` with no lock. Python docs: writes must be serialized by the user.
- [ ] **F07 Require `ADMIN_TELEGRAM_ID` at startup** — empty value makes every command a silent no-op.
- [ ] **F09 Compose flags for Chromium** — Playwright Docker docs: `init: true`, `ipc: host` (or `shm_size`), seccomp with non-root. Also F13: bind-mounted `./data`/`./logs` may be root-owned on Linux so `appuser` cannot write.
- [ ] **F10 Drop the unused startup browser** — `init_browser()` is not reused by `poll_job`. Replace `time.sleep` while Playwright is live (`page.wait_for_timeout` or sleep only between launches).
- [ ] **F11 Do not wait for `networkidle`** — Playwright marks it discouraged; live pages load Google Analytics. Wait for `a[href*="/annonces/"]` (or the new list selector).
- [ ] **F14 `deleteWebhook` at boot; log getUpdates failures at ERROR; increment offset after handle** — leftover webhooks make commands silently dead. Extra `sleep(2)` after a 10s long poll is unnecessary.

### 6.3 Config / docs drift (fix code or fix docs, not both left lying)

- [ ] **F21 Dead knobs** — no YAML←env overlay; `POLL_INTERVAL` unused; YAML `retry:` unused (tenacity hardcoded); `content_area` unused; `seen_at` never passed.
- [ ] **F22 DB path** — `database.path: /app/data/notices.db` is Docker-only. Use a path relative to `BASE_DIR`.
- [ ] **F19 Dedup docs** — README says SHA256 of `url + title`; code keys on `url` only. Align. `/subscribe Informatique` in README does not match English labels (`Computer Science`).
- [ ] **F12 Healthcheck** — 6h SQLite `connect()` does not prove the bot is polling and can create an empty DB file. Touch a heartbeat file per successful poll; minutes-scale interval.
- [ ] **F16 Heartbeat / selector warnings** — currently posted to the public channel. Send to admin DM.

### 6.4 Tests that would have caught the above (F17)

- [ ] Fixture HTML: parse count equals all `/annonces/` links, not 7 carousel slides
- [ ] Seed / first-run: empty DB → zero Telegram calls
- [ ] Send failure → URL remains unseen
- [ ] Title containing `*` / `_` / `<` does not 400
- [ ] Every department `callback_data` ≤ 64 bytes
- [ ] `validate_env` rejects missing admin
- [ ] `extract_date` on `02جوان 2025` (no space) — F18

### 6.5 Optional (not required to deploy 6.1)

- [ ] F04: log carousel slides that have a title but no URL
- [ ] F15: delay per chat (~1s); honor 429 `Retry-After`
- [ ] F18: optional whitespace in date regex
- [ ] F20: `link_preview_options` instead of `disable_web_page_preview`
- [ ] Prove `requests` + lxml vs Playwright on this site; drop Chromium if static HTML is enough

---

## Phase 7 – Integration and deploy

Only after 6.1 is done.

- [ ] **7.1** `docker compose build && docker compose up -d` against a **private test channel**
- [ ] **7.2** Confirm first cycle seeds with no flood; second cycle with a fixture/new URL sends one message
- [ ] **7.3** Confirm `/subscribe` Computer Science button works (callback_data fix)
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
│   ├── test_database.py
│   ├── test_utils.py
│   └── test_config.py
├── docs/
│   └── RESEARCH-ISSUES.md   # cited bug list
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── README.md
└── PLAN.md
```

`src/__init__.py` / `tests/__init__.py` may exist as empty files (research F-list); they are not required for `python -m src.main`.
