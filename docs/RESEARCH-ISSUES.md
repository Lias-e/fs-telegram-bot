# Research: known issues in fs-telegram-bot

- **Date:** 2026-09-11
- **Scope:** Correctness, dedup/first-run, Telegram Bot API usage, Playwright scraping vs live HTML, Docker/runtime, config/env, tests, security.
- **Method:** Primary sources only. Claims below are traced to this repo’s source, official Telegram / Playwright / Docker / Python sqlite3 documentation, and HTML fetched from `https://fsciences.univ-setif.dz` and `https://fsciences.univ-setif.dz/sites_departements/informatique` on 2026-09-11. Runtime of Docker/Chromium and live `sendMessage` were **not** executed; where a claim depends on that, it is marked unverified.

## Findings

### F01 — Insert-before-send permanently drops failed broadcasts

- **Severity:** blocker
- **Summary:** A notice is written to SQLite as seen *before* Telegram delivery. If `sendMessage` fails, the next poll treats it as a duplicate and never retries.
- **Evidence:**
  - `src/main.py` 80–90: `is_duplicate(url)` → `insert_notice(...)` → `broadcaster.send(...)`.
  - `src/database.py` 50–64, 62–64: `INSERT OR IGNORE`; `is_duplicate` is `SELECT 1 FROM notices WHERE url = ?`.
  - `src/broadcaster.py` 38–48: `_send_to_chat` catches exceptions, logs, and does not re-raise; caller cannot know that send failed.
  - Telegram `sendMessage` is documented to reject bad parse entities with a failed request (`https://core.telegram.org/bots/api#sendmessage`, formatting options). Combined with F05, a Markdown 400 is a realistic failure mode.
- **Impact:** A new notice can be recorded and never appear in any chat. There is no outbox, retry queue, or “sent” flag.
- **Recommended fix:** Insert only after a successful send, or insert with a `sent_at`/`status` column and retry unsent rows. Treat send failure as failure of the whole item.

### F02 — First poll broadcasts the entire current listing

- **Severity:** high
- **Summary:** There is no quiet seed. Startup scrapes once for selector validation (does not insert), then `run_poll()` immediately sends every URL not already in the DB. An empty database therefore broadcasts every currently listed carousel notice.
- **Evidence:**
  - `src/main.py` 155–159: startup `scrape_all` used only to warn if empty; no `insert_notice`.
  - `src/main.py` 208: `run_poll()` is invoked as soon as the scheduler starts.
  - `src/main.py` 78–90: every non-duplicate is inserted and sent.
  - Live main page carousel (fetched 2026-09-11) contains multiple existing `/annonces/{id}` items (e.g. 9335, 9334, 9329, 9321, 7994, 7180).
- **Impact:** First deploy/reset floods the channel (and subscribed chats) with historical carousel items, then hits F01/F17 if Telegram returns 429. PLAN.md Phase 5.3 (“Verify first notice appears in Telegram channel”) does not describe seeding vs broadcasting.
- **Recommended fix:** On empty DB, insert all scraped URLs without sending (or send only items newer than a cutoff). Keep the validation scrape, but persist hashes before enabling broadcast.

### F03 — Selectors only match the Bootstrap carousel, not most notices on the main page

- **Severity:** high
- **Summary:** `notice_container` is `div.item`. On the live faculty homepage that matches the carousel slides only. Most `/annonces/` links live in later `h3` list panels and are never parsed.
- **Evidence:**
  - `config/selectors.json` 7–11: `"notice_container": "div.item"`, `"link": "a[href*='/annonces/']"`.
  - `src/scraper.py` 43–74: iterates `cssselect(notice_container)`, skips elements with no link.
  - Live `https://fsciences.univ-setif.dz` HTML (2026-09-11):
    - 7 `class="item"` nodes, all inside `#carousel-example-generic` (carousel).
    - 31 `href="/annonces/..."` links on the page.
    - Carousel-linked IDs: 9335, 9334, 9329, 9321, 7994, 7180 (plus one slide with **no** link; see F04).
    - List-panel notices **not** in `div.item`, including IDs newer than some carousel slides: 9333, 9330, 9326, 9324, 9323 (and many older ones 8165, 8164, 7886, …).
  - CS department page `https://fsciences.univ-setif.dz/sites_departements/informatique` (2026-09-11): carousel uses the same `div.item` + `/annonces/` pattern (3 slides: 9311, 9310, 9085). Those three would be scraped; staff listings below are not `/annonces/` links.
- **Impact:** The bot’s stated job is monitoring administrative notices on the main page + departments. On the main page it only sees featured carousel slides. Notices published only in the pedagogy / international / events panels are invisible.
- **Recommended fix:** Add selectors for the `h3` + `a[href^="/annonces/"]` list panels (or scrape all `a[href*="/annonces/"]` with a nearby heading). Re-validate `config/selectors.json` `_meta` against live HTML; `validated: true` / `last_updated: 2026-06-20` is stale relative to this structure.

### F04 — Active carousel slide on the main page has no notice URL

- **Severity:** medium
- **Summary:** The first main-page carousel slide has title/date markup but no `/annonces/` anchor, so `parse_notices` discards it.
- **Evidence:**
  - Live HTML (2026-09-11), first slide: `<div class="item active">` contains `<h2>التسجيلات في السنة الاولى ماستر</h2>` and `<h3>أخر أجل للتسجيل</h3>` and no `a[href*="/annonces/"]`.
  - `src/scraper.py` 59–64: `href = link_el[0].get("href") if link_el else None` then `if not url: continue`.
- **Impact:** That featured item is never broadcast. If the CMS often publishes the newest slide without a link, the most visible notice is the one the bot skips.
- **Recommended fix:** Log skipped slides (title without URL). If the site later adds a link, current code will pick it up; until then, consider a fallback (e.g. hash of title+date) only if product intent is to notify even without a URL.

### F05 — Legacy Markdown `parse_mode` on unescaped site text

- **Severity:** high
- **Summary:** Broadcasts and command replies set `parse_mode` to legacy `Markdown` and interpolate titles/URLs without escaping. Telegram documents that `_`, `*`, `` ` ``, `[` must be escaped outside entities, and that escaping **inside** entities is not allowed.
- **Evidence:**
  - `src/broadcaster.py` 27–31: `"parse_mode": "Markdown"`.
  - `src/commands.py` 50: same.
  - `src/utils.py` 61–66, 69–78: `f"📄 *{title}*"` and `[Open Notice]({url})` with no escaping.
  - `src/heartbeat.py` 42: `f"- [{row['title'] or 'Untitled'}]({row['url']})"`.
  - Official API (`https://core.telegram.org/bots/api#markdown-style`): legacy Markdown; “To escape characters `_`, `*`, `` ` ``, `[` outside of an entity, prepend `\`”; “Escaping inside entities is not allowed”.
  - Official API (`https://core.telegram.org/bots/api#sendmessage`): `text` is 1–4096 characters **after entities parsing**; failed entity parsing rejects the method.
  - Live titles sampled 2026-09-11 (Arabic headings, `CALL FOR PAPERS`, `GLOBAL CONSUMER INTELLIGENCE 2026`, French `AUX ÉTUDIANTS...`) did **not** contain `*`, `_`, or `[`. The failure mode is therefore latent for this sample, not observed on those strings.
- **Impact:** Any future title with `*` / `_` / `[`, or a URL with `)`, can 400 the send. With F01, that notice is then stuck as “seen”. Heartbeat can fail the same way.
- **Recommended fix:** Use `parse_mode=HTML` and escape `& < >` in titles (API HTML style: `https://core.telegram.org/bots/api#html-style`), or send without `parse_mode` / use `entities`. Do not wrap untrusted text in `*...*` or `[...](url)` using legacy Markdown.

### F06 — Inline keyboard `callback_data` exceeds the 64-byte API limit

- **Severity:** high
- **Summary:** Department toggle buttons put the full URL in `callback_data`. The Computer Science URL is 68 bytes with the `dept|` prefix. Telegram allows 1–64 bytes. One oversized button fails the whole `sendMessage` markup.
- **Evidence:**
  - `src/commands.py` 70–78: `callback_data` is `f"dept|{url}"` for every target.
  - Official API InlineKeyboardButton (`https://core.telegram.org/bots/api#inlinekeyboardbutton`): `callback_data` … “1-64 bytes”.
  - Byte lengths (ASCII, UTF-8):
    - `dept|https://fsciences.univ-setif.dz` → 36
    - `dept|https://fsciences.univ-setif.dz/sites_departements/informatique` → **68** (over)
    - `dept|https://fsciences.univ-setif.dz/sites_departements/physique` → 64 (at the limit)
    - `dept|https://fsciences.univ-setif.dz/sites_departements/chimie` → 62
    - maths / mi / sm are shorter.
  - `/subscribe` and `/unsubscribe` with no args both send this keyboard (`src/commands.py` 159–165, 184–189).
- **Impact:** The department toggle UI is expected to 400 when the CS target is in `settings.yaml` (it is). Text `/subscribe <name>` still works if the name matches a **label** (see doc mismatches). This research did not POST to Telegram to capture the error body.
- **Recommended fix:** Put a short id in `callback_data` (e.g. `dept|informatique`) and map it server-side. Keep payloads well under 64 bytes.

### F07 — `ADMIN_TELEGRAM_ID` is not required; empty admin silences every command

- **Severity:** high
- **Summary:** README lists `ADMIN_TELEGRAM_ID` as required. `validate_env()` does not. If the var is missing or `""` (as in `.env.example`), `_is_admin` is never true and commands are dropped with no reply.
- **Evidence:**
  - `src/config.py` 30–34: required = `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID` only.
  - `src/main.py` 165: `admin_id=get_env("ADMIN_TELEGRAM_ID", None)`.
  - `src/commands.py` 94–105: `_is_admin` is `admin_id is not None and str(user_id) == str(self.admin_id)`; non-admin `return` with no message.
  - Callbacks do answer “Not authorized” (`src/commands.py` 217–218); messages do not.
  - `.env.example` line 6: `ADMIN_TELEGRAM_ID=` (empty).
  - README “Environment Variables”: `ADMIN_TELEGRAM_ID` | Yes.
- **Impact:** A copied `.env.example` yields a bot that broadcasts but appears dead to `/start` and every other command. No startup warning.
- **Recommended fix:** Require `ADMIN_TELEGRAM_ID` in `validate_env()`. Reject empty strings. Reply “not authorized” on ignored commands (optional). Fail fast at boot.

### F08 — Shared SQLite connection across threads without serialized writes

- **Severity:** high
- **Summary:** One `sqlite3` connection is used from the main thread, APScheduler worker threads, and the command-handler thread, with `check_same_thread=False` and no application lock.
- **Evidence:**
  - `src/database.py` 39: `sqlite3.connect(db_path, check_same_thread=False)`.
  - Users of that connection: `poll_job` (`src/main.py` 59–88), `CommandHandler` thread (`src/main.py` 167–168, `src/commands.py`), `heartbeat_job` (`src/heartbeat.py` 32–33), `backup_job` (`src/database.py` 119–127 `conn.backup`).
  - Python 3 `sqlite3.connect` docs (`https://docs.python.org/3/library/sqlite3.html#sqlite3.connect`): if `check_same_thread` is `False`, “the connection may be accessed in multiple threads; **write operations may need to be serialized by the user to avoid data corruption**.”
  - Same page, `sqlite3.threadsafety`: SQLite “multi-thread” mode still requires that **no single connection is used simultaneously in two or more threads**.
- **Impact:** Concurrent `/subscribe` (writes `settings` / `subscriptions`) vs poll insert vs heartbeat read vs `backup()` can raise `OperationalError` or, per the Python docs, corrupt data if overlapping writes are not serialized. This research did not reproduce a corruption event.
- **Recommended fix:** One connection per thread, or a `threading.Lock` around all `execute`/`commit`/`backup`, or `sqlite3.connect` URI `mode=...` plus WAL **and** a mutex. Do not share one connection unsynchronized.

### F09 — Playwright Docker runtime: no `--ipc=host` / `shm`, no `init`, non-root without seccomp

- **Severity:** high (runtime crash **not** reproduced in this research)
- **Summary:** Official Playwright Python Docker docs recommend `--ipc=host` (or equivalent) for Chromium, `--init` to reap zombies, and a seccomp profile when running browsers as a non-root user. This Compose file has none of those. Chromium is launched with default sandbox flags.
- **Evidence:**
  - `docker-compose.yml`: no `ipc`, `shm_size`, `init`, `security_opt`, or memory limit. Healthcheck only.
  - `Dockerfile` 21–31: `useradd appuser` then `USER appuser`. `install-deps` runs **before** `USER` (root), which matches Playwright’s “install-deps as root” guidance (`https://playwright.dev/python/docs/browsers#install-system-dependencies`).
  - `src/main.py` 54, 65: `chromium.launch(headless=True)` with no launch args.
  - Playwright Python Docker (`https://playwright.dev/python/docs/docker`):
    - “Using `--ipc=host` is recommended when using Chromium. Without it, Chromium can run out of memory and crash.”
    - “Using `--init` … is recommended to avoid special treatment for processes with PID=1” (zombie processes).
    - For crawling/scraping: “create a separate user … in combination with the seccomp profile.”
  - Compose `init` (`https://docs.docker.com/reference/compose-file/services/#init`): runs an init that “forwards signals and reaps processes.”
  - Docker memory docs (`https://docs.docker.com/engine/containers/resource_constraints/`): a container with no memory limit can trigger host OOM; Chromium is not memory-capped here.
  - Official “build your own image” example uses `python:3.12-bookworm` and `playwright install --with-deps`, not `python:3.10-slim` with a split copy of `site-packages`. Difference is noted; image **build/run was not executed** here.
- **Impact:** Chromium launch failures, crashes from small `/dev/shm`, zombie browser processes, or host OOM are consistent with the official warnings. Unverified on this machine.
- **Recommended fix:** Follow Playwright’s Docker page: `init: true`, `ipc: host` (or `shm_size`), pin a Playwright base image or `install --with-deps` on bookworm, keep `install-deps` as root, and either run Chromium with the documented seccomp profile or the official `pwuser` setup. Add a memory limit only after measuring Chromium RSS.

### F10 — Startup Chromium is leaked; poll opens a second browser; `time.sleep` on the Playwright thread

- **Severity:** medium
- **Summary:** `init_browser()` starts a process used only for the startup scrape, then left open. Each poll starts another Playwright/Chromium. Delays use `time.sleep` while a browser is alive.
- **Evidence:**
  - `src/main.py` 50–56, 142–146: global `_browser` launched; `Scraper(browser, ...)` for validation only.
  - `src/main.py` 63–67: `poll_job` does `with sync_playwright() as pw: browser = pw.chromium.launch(...)` — a second instance, not `_browser`.
  - `src/scraper.py` 17–22, 24–25: `_random_delay()` is `time.sleep` **before** `new_context`, including on URLs 2–7 while the poll browser is already open.
  - Playwright Python library (`https://playwright.dev/python/docs/library`): “Playwright’s API is not thread-safe. … create a playwright instance per thread.” Poll’s per-job instance is consistent with that. Same page: “`time.sleep()` leads to outdated state” because the driver needs the thread to process async work; they tell you to use `page.wait_for_timeout` instead.
  - Shutdown (`src/main.py` 123–125) closes `_browser` only, not an in-flight poll browser (poll’s `with` should still close on generator teardown unless the process is hard-killed).
- **Impact:** Extra RAM for an idle Chromium for the life of the process. `time.sleep` during an active sync Playwright session is officially discouraged and can cause flaky timeouts. Unverified at runtime.
- **Recommended fix:** Do not keep a global browser, or reuse one instance **on a single dedicated thread**. Replace `time.sleep` with `page.wait_for_timeout` or sleep only when no Playwright instance is running on that thread.

### F11 — `networkidle` wait on pages that load Google Analytics

- **Severity:** medium
- **Summary:** After `goto`, the scraper waits for `networkidle`. Playwright marks that state as discouraged. Live pages include Google tag (`gtag.js` / `UA-159474485-1`), which can keep network activity open.
- **Evidence:**
  - `src/scraper.py` 31–32: `page.goto(..., timeout=timeout_seconds*1000)` then `page.wait_for_load_state("networkidle")`.
  - Playwright Page API (`https://playwright.dev/python/docs/api/class-page`): `'networkidle'` is **DISCOURAGED** — “no network connections for at least 500 ms.”
  - Live CS department HTML head (2026-09-11): `googletagmanager.com/gtag/js?id=UA-159474485-1` and `gtag('config', 'UA-159474485-1')`. Main page uses the same pattern in the fetched file.
  - On exception, `fetch_page` returns `None` (`src/scraper.py` 36–38), so that URL contributes zero notices for the cycle (`src/scraper.py` 78–82).
- **Impact:** If analytics/long-polling prevents 500 ms of idle, the 30s wait times out and the whole target is skipped for that poll. Not reproduced with Playwright in this research.
- **Recommended fix:** Wait for a locator that exists in `selectors.json` (e.g. `div.item` or `a[href*="/annonces/"]`) instead of `networkidle`.

### F12 — Healthcheck does not observe the bot process and can create an empty DB file

- **Severity:** medium
- **Summary:** The Compose healthcheck opens `/app/data/notices.db` with Python `sqlite3`. Interval is 6 hours. `restart: always` restarts on process exit, not on `unhealthy`. `sqlite3.connect` on a missing path creates a file.
- **Evidence:**
  - `docker-compose.yml` 10–15: `python -c "... sqlite3.connect('/app/data/notices.db').execute('SELECT 1')"`; `interval: 6h`.
  - Compose healthcheck (`https://docs.docker.com/reference/compose-file/services/#healthcheck`): declares container health; example interval in the same docs is `1m30s`.
  - Python `sqlite3.connect` (`https://docs.python.org/3/library/sqlite3.html`): opens a database file at that path (creates if absent — standard SQLite open behavior).
  - A hung `threading.Event().wait()` (`src/main.py` 212) with a dead scheduler still looks healthy if the DB file exists.
- **Impact:** Health status is a weak SQLite probe, at most every 6 hours. A healthcheck that runs before the app creates the schema can leave an empty `notices.db` on the volume (race; not observed).
- **Recommended fix:** Check a PID/heartbeat file the app touches each successful poll, or `SELECT` a known table after start. Use a minutes-scale interval. Do not `connect()` a path the app has not created yet.

### F13 — Bind-mounted `data/` / `logs/` vs non-root `appuser`

- **Severity:** medium (Linux Engine permission failure **not** reproduced here)
- **Summary:** The image creates `/app/data` and `/app/logs` as `appuser`, then Compose bind-mounts `./data` and `./logs` over them. Docker bind-mounts hide the image’s directories and use host ownership.
- **Evidence:**
  - `Dockerfile` 21–23, 31: `mkdir -p /app/data /app/logs`, `chown -R appuser:appuser /app`, `USER appuser`.
  - `docker-compose.yml` 7–9: `./data:/app/data`, `./logs:/app/logs`.
  - Docker bind mounts (`https://docs.docker.com/engine/storage/bind-mounts/`): mounting into a non-empty container dir **obscures** image contents; `-v` creates a missing host path as a **directory**.
  - `src/main.py` 29–30, `src/database.py` 38, `src/config.py` via `settings.yaml` 39–41: the process writes `logs/app.log` and `/app/data/notices.db`.
- **Impact:** On Linux Engine, a Compose-created `./data` is often root-owned; `appuser` then cannot create the SQLite file or log file and the container crash-loops. Docker Desktop/Windows behavior differs (docs note Desktop path mapping). Not executed here.
- **Recommended fix:** Document `chown` of `data/` and `logs/` to the container UID, or run an entrypoint that fixes ownership, or use a named volume.

### F14 — getUpdates: failures hidden at DEBUG; extra sleep; no `deleteWebhook`

- **Severity:** medium
- **Summary:** Long polling is used correctly in outline (offset = `update_id + 1`), but errors are logged at DEBUG, every cycle sleeps 2s after the HTTP call, and nothing calls `deleteWebhook`.
- **Evidence:**
  - `src/commands.py` 243–267: `getUpdates` with `timeout: 10`, httpx timeout 15, then `time.sleep(2)` in `run_forever`.
  - `src/commands.py` 257–258: `except Exception: logger.debug("getUpdates poll: %s", e)` — default `LOG_LEVEL=INFO` (`README`, `.env.example`) hides these.
  - Offset is incremented **before** `_handle` (`src/commands.py` 251–256). If `_handle` raises, Telegram will not redeliver that update (`https://core.telegram.org/bots/api#getupdates`: an update is confirmed once `getUpdates` is called with a higher offset). Official FAQ (`https://core.telegram.org/bots/faq`): “offset = update_id of last processed update + 1”.
  - Same API page, getUpdates notes: “This method will not work if an outgoing webhook is set up.” There is no `deleteWebhook` in this repo. Official FAQ: “it’s not possible to get updates via long polling while an outgoing Webhook is set.”
- **Impact:** A leftover webhook (from earlier experiments) would make commands silently do nothing. Transient API errors are invisible at INFO. A crashing handler loses the update.
- **Recommended fix:** Call `deleteWebhook` at startup. Log getUpdates failures at ERROR. Increment offset after successful handling (or catch around `_handle`). Remove the extra 2s sleep (long poll already blocks up to 10s).

### F15 — Inter-chat send burst vs documented Telegram limits

- **Severity:** medium
- **Summary:** There is a 3s pause *between notices*, not between chats. `send()` walks every `chat_id` with no delay. FAQ limits: about 1 message/second per chat, 20/min in a group, ~30/sec bulk.
- **Evidence:**
  - `src/main.py` 88–92: `broadcaster.send(text, chat_ids=chat_ids)` then `if new_count > 0: time.sleep(3)` (always true after increment).
  - `src/broadcaster.py` 50–54: sequential `_send_to_chat` per id, no sleep between chats (sleep only between split parts, lines 42–43).
  - Official FAQ (`https://core.telegram.org/bots/faq`): “In a single chat, avoid sending more than one message per second”; “In a group, bots are not be able to send more than 20 messages per minute”; bulk ~30/sec then 429.
- **Impact:** With one channel, 3s/notice is within per-chat guidance. With many subscribed chats, first-run (F02) can burst. 429s plus F01 drop notices. `tenacity` retries 3 times (`src/broadcaster.py` 21–24) without reading `Retry-After`.
- **Recommended fix:** Delay per chat (~1s). On 429, honor Retry-After. Do not mark a notice seen until all required destinations succeed (or persist per-chat send state).

### F16 — Heartbeat and selector warnings go to the public channel

- **Severity:** medium
- **Summary:** `Broadcaster.send()` without `chat_ids` uses `TELEGRAM_CHANNEL_ID`. Heartbeat (every 6h) and the startup selector warning therefore post into the announcement channel, not an admin DM.
- **Evidence:**
  - `src/broadcaster.py` 50–52: default `[self.default_chat_id]`.
  - `src/heartbeat.py` 43: `self.broadcaster.send(...)`.
  - `src/main.py` 159: warning send with Markdown.
  - `config/settings.yaml` 23–24: heartbeat every 6 hours.
- **Impact:** Subscribers see ops messages (`🤖 Bot Heartbeat`, selector warnings). If Markdown in heartbeat titles fails (F05), the health ping 400s and is only logged.
- **Recommended fix:** Send ops traffic to `ADMIN_TELEGRAM_ID` (private chat). Keep the channel for notices only.

### F17 — Tests do not cover the real failure modes

- **Severity:** medium
- **Summary:** Unit tests cover DB CRUD, hashing, `split_text`, YAML load. They do not cover poll ordering, first-run, scraper vs HTML, Telegram parse_mode, commands/admin, `callback_data` length, or `extract_date`.
- **Evidence:**
  - `tests/test_database.py`: init, insert/dedup, subscriptions, settings. No concurrency, no backup-during-write.
  - `tests/test_utils.py`: `sha256_hash`, `split_text`, `format_notice`. No `format_notice_with_seen`, no `extract_date`, no Markdown/HTML escaping.
  - `tests/test_config.py`: keys exist in YAML/JSON; `get_env` helper. No `validate_env` missing-admin case. No env overlay (PLAN claimed overlay; see mismatches).
  - No tests import `scraper`, `broadcaster`, `commands`, `main.poll_job`.
  - PLAN.md 87–95: integration test and deploy still unchecked.
- **Impact:** F01–F06 can regress without a red test. `test_split_text_over_limit` does not assert Telegram’s 4096-after-parse rule or mid-entity splits (`src/utils.py` 33–48, `config/settings.yaml` `message_max_length: 4000`).
- **Recommended fix:** Fixture HTML from the live pages; assert parse counts (carousel vs all `/annonces/`). Test poll: mock send failure → row not marked seen. Test `callback_data` `len(encode()) <= 64`. Test `validate_env` for admin. Test `extract_date` including `02جوان 2025` (no space).

### F18 — Date extraction is brittle; caption `h3` is often not a date

- **Severity:** low
- **Summary:** Dates are parsed with a regex that requires whitespace between day and month. The CSS date field is `.carousel-caption h3`, which on live pages is often a subtitle, not a calendar date.
- **Evidence:**
  - `src/utils.py` 23–26, 51–58: `(\d{1,2})\s+(months)\s+(\d{4})`.
  - Live main page list text `المنشور رقم 1 ( 02جوان 2025)` — digit run against `جوان` with **no space**; this pattern does not match.
  - Live CS carousel: `<h3>Résultat de l'Orientation </h3>` used as date (`config/selectors.json` `"date": ".carousel-caption h3"`). `extract_date` on that string returns `""`.
  - Live main carousel item with `<h3>قبل 10 سبتمبر 2026</h3>`: `10 سبتمبر 2026` **does** match (`سبتمبر` is in `MONTH_MAP`).
  - `src/main.py` 87: `extract_date(notice["title"] + " " + notice["date"])`.
  - No unit tests for `extract_date`.
- **Impact:** Many messages omit 📅. Functional broadcast still works if the URL exists.
- **Recommended fix:** Allow optional whitespace; if caption `h3` is not a date, leave date empty rather than showing the subtitle as if it were one (today the subtitle is only used as extract input, not printed unless the regex matches).

### F19 — Dedup key is URL; hash is unused; README/PLAN disagree with code

- **Severity:** medium (behavior) / see also Doc/plan mismatches
- **Summary:** README says SHA256 of `url + title`. Code hashes URL only and keys the table on `url`. Title edits at the same URL are not new notices; the `hash` column is never queried.
- **Evidence:**
  - README line 9: “SHA256 hashing of `url + title`”.
  - PLAN.md 32–33: `insert_notice(id, url, title, hash)`; `is_duplicate(hash)`.
  - `src/main.py` 82–86: `is_duplicate(url)`; `sha256_hash(url)`.
  - `src/database.py` 8–14, 62–64: `url TEXT PRIMARY KEY`; lookup by `url`.
- **Impact:** Same notice URL with a changed title will not re-broadcast (URL-key is a valid design, but not the documented one). Distinct URLs for the same notice (http/https, trailing slash) would double-post; live hrefs are site-relative `/annonces/{id}` joined with `urljoin` (`src/scraper.py` 60), which is consistent if the base URL is stable.
- **Recommended fix:** Align docs with URL primary key, or hash `url + title` and decide what a “title change” should do.

### F20 — `sendMessage` still sends `disable_web_page_preview`

- **Severity:** low
- **Summary:** Current Bot API `sendMessage` table lists `link_preview_options`, not `disable_web_page_preview`. The client still sends the old field.
- **Evidence:**
  - `src/broadcaster.py` 31: `"disable_web_page_preview": False`.
  - Fetched Bot API (2026-09-11) `sendMessage` parameters: `link_preview_options` present; **no** `disable_web_page_preview` in that dump (`https://core.telegram.org/bots/api#sendmessage`).
- **Impact:** Unknown fields are typically ignored by Telegram (not verified with a live POST). Previews stay at API default. Not a crash by itself.
- **Recommended fix:** Use `link_preview_options` as documented if preview control is required.

### F21 — Dead / unused configuration in code

- **Severity:** low
- **Summary:** Several planned knobs are loaded or documented but not applied.
- **Evidence:**
  - PLAN.md 27: “Overlay with environment variables (env wins).” `src/config.py` `load_settings()` returns YAML only (lines 14–17). `POLL_INTERVAL` in `.env.example` is never read. `TARGET_URL` is only a fallback if `poll.targets` is missing (`src/main.py` 60, 153).
  - `config/settings.yaml` `retry:` is unused; tenacity parameters are hardcoded on the decorator (`src/broadcaster.py` 21–24).
  - `format_notice_with_seen(..., seen_at="")` (`src/utils.py` 69–75): `poll_job` never passes `seen_at` (`src/main.py` 88), so the “Detected:” branch is dead.
  - `selectors.json` `content_area` is never read by `scraper.py`.
- **Impact:** Operators editing `.env` `POLL_INTERVAL` or YAML `retry` get no effect. Confusion, not a runtime exception.
- **Recommended fix:** Overlay env in `load_settings`, or delete unused keys from `.env.example` / YAML.

### F22 — `settings.yaml` database paths assume the Docker layout

- **Severity:** medium
- **Summary:** DB paths are absolute `/app/data/...`. README’s local run (`PYTHONPATH=... python -m src.main`) on Windows/Linux without that directory writes outside the project (or fails).
- **Evidence:**
  - `config/settings.yaml` 39–41: `path: /app/data/notices.db`, `backup_dir: /app/data/backup`.
  - README 60–64: local venv instructions; no Docker-path caveat.
  - `src/database.py` 38: `Path(db_path).parent.mkdir(parents=True, exist_ok=True)` — will try to create `/app/data` (on Windows, a drive-root `\app\data`).
- **Impact:** Local README path does not match config. Docker is consistent with `/app`.
- **Recommended fix:** Relative paths from `BASE_DIR` (`src/config.py` 10), e.g. `data/notices.db`, which also works in the image if `WORKDIR` is `/app`.

## Doc/plan mismatches

| Topic | README | PLAN.md | Code |
| --- | --- | --- | --- |
| Dedup | SHA256 of `url + title` | `is_duplicate(hash)`; `insert_notice(id, url, title, hash)` | URL primary key; hash of URL only; hash not queried (F19) |
| Env overlay | Table: token, channel, admin, `LOG_LEVEL` | `.env.example` also `TARGET_URL`, `POLL_INTERVAL`; “env wins” over YAML | No YAML overlay; `POLL_INTERVAL` unused; `TARGET_URL` fallback only (F21) |
| Required env | `ADMIN_TELEGRAM_ID` required | Phase 1.3 `.env.example` had no admin (later added in file) | Not in `validate_env()` (F07) |
| `/subscribe` | `/subscribe Informatique`, `/unsubscribe Maths` | (commands module not in Phase 2 list; file exists) | Labels are English: “Computer Science”, “Mathematics”. `"informatique" in "computer science"` is false; `"maths" in "mathematics"` is false (`src/commands.py` 8–16, 167–173). Button UI is the working path (blocked by F06). |
| Adaptive poll | 5 min if new, else 30 | Same | Matches `settings.yaml` `fast_interval_minutes: 5`, `default_interval_minutes: 30` |
| Telegram delay | “3s delay between” chats | — | 3s between **notices**, not chats (F15) |
| Architecture | getUpdates every 2s | — | Long poll 10s **plus** sleep 2s (F14) |
| `commands.py` | Listed in structure | Phase 2 file list originally omits it; later “Files Created” still omits `commands.py` | Present |
| `__init__.py` | Not mentioned | Listed under `src/` and `tests/` | `src/__init__.py` and `tests/__init__.py` are empty files (readable; glob may omit empties) |
| Selectors `_meta.validated` | — | Initially `false` | `true`, `last_updated: 2026-06-20` — live HTML still carousel-only for `div.item` (F03) |
| DB path | Implied project `data/` | `data/` in tree | `/app/data/notices.db` (F22) |
| Healthcheck | “health checks” | “every 6h” | Matches PLAN; weak probe (F12) |
| Integration tests | — | 5.2 / 5.3 unchecked | No scraper/Telegram/Docker tests (F17) |
| Retry YAML | — | tenacity from settings | Hardcoded decorator (F21) |

## Sources

### This repository

- `src/main.py`
- `src/scraper.py`
- `src/broadcaster.py`
- `src/commands.py`
- `src/database.py`
- `src/config.py`
- `src/heartbeat.py`
- `src/utils.py`
- `src/__init__.py` (empty)
- `config/settings.yaml`
- `config/selectors.json`
- `tests/test_database.py`
- `tests/test_utils.py`
- `tests/test_config.py`
- `tests/__init__.py` (empty)
- `Dockerfile`
- `docker-compose.yml`
- `requirements.txt`
- `.env.example`
- `.gitignore`
- `README.md`
- `PLAN.md`

### Official documentation (fetched 2026-09-11)

- Telegram Bot API: `https://core.telegram.org/bots/api`  
  (getUpdates, sendMessage, formatting / Markdown style, InlineKeyboardButton `callback_data`, 4096-character text)
- Telegram Bots FAQ: `https://core.telegram.org/bots/faq`  
  (long polling vs webhook, broadcast rate limits)
- Playwright Python library: `https://playwright.dev/python/docs/library`  
  (thread safety, `time.sleep`)
- Playwright Page API: `https://playwright.dev/python/docs/api/class-page`  
  (`networkidle` discouraged)
- Playwright Docker: `https://playwright.dev/python/docs/docker`  
  (`--ipc=host`, `--init`, non-root + seccomp, sample Dockerfile with `--with-deps`)
- Playwright browsers / install-deps: `https://playwright.dev/python/docs/browsers#install-system-dependencies`
- Playwright CI Docker note: `https://playwright.dev/python/docs/ci#docker`
- Python `sqlite3`: `https://docs.python.org/3/library/sqlite3.html`  
  (`check_same_thread`, `threadsafety`)
- Docker Compose services: `https://docs.docker.com/reference/compose-file/services/#healthcheck`, `#init`
- Docker bind mounts: `https://docs.docker.com/engine/storage/bind-mounts/`
- Docker resource constraints: `https://docs.docker.com/engine/containers/resource_constraints/`
- Dockerfile `USER`: `https://docs.docker.com/reference/dockerfile/#user`

### Live site (fetched 2026-09-11)

- `https://fsciences.univ-setif.dz` (full HTML via HTTP GET)
- `https://fsciences.univ-setif.dz/sites_departements/informatique` (full HTML via HTTP GET)

Not used as evidence: blogs, Stack Overflow, GitHub issues, or unofficial Telegram/Playwright write-ups.
