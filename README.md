# University Broadcaster Telegram Bot

Autonomous pipeline that polls the **University of Setif 1 – Faculty of Sciences** website (main page + 6 department sub-pages) for new administrative notices and broadcasts them to a Telegram channel with URL-based duplicate detection and department-level filtering.

**Do not deploy until Phase 6 defects are verified** — see [`PLAN.md`](PLAN.md) and [`docs/RESEARCH-ISSUES.md`](docs/RESEARCH-ISSUES.md).

## Features

- **Multi-target monitoring** – scrapes the main page + 6 departments (CS, Math, Physics, Chemistry, MI, SM)
- **Adaptive polling** – checks every 5 min if new notices were found, otherwise every 30 min
- **Duplicate prevention** – SQLite `notices.url` primary key
- **Quiet first run** – empty DB seeds all current URLs without flooding the channel
- **Send-then-record** – a notice is marked seen only after a successful send to the channel
- **Multi-chat broadcasting** – sends to the default channel + all subscribed chats/groups
- **Admin-only commands** – only the configured admin user can control the bot
- **Department filtering** – enable/disable individual departments via `/subscribe` / `/unsubscribe`
- **Static HTML fetch** – httpx + lxml (Playwright not required for this site)
- **Resilient** – poll heartbeat file, file rotation logging, dynamic selector config, tenacity retry
- **Zero cost** – designed for self-hosting on a local Linux server

## Architecture

```
[University Website (7 URLs)]
         ↓
[httpx Scraper]  →  lxml parsing →  all /annonces/ links
         ↓
[SQLite State]
  ├─ notices table (URL primary key)
  ├─ subscriptions table (chat IDs)
  └─ settings table (disabled departments)
         ↓
[httpx + Telegram API]  →  HTML messages to channel + subscribed chats (3s between notices)
         ↑
[Command Handler]  ←  getUpdates long poll (deleteWebhook at boot)
```

## Prerequisites

- Python 3.10+
- Docker & Docker Compose (recommended for deployment)
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- A Telegram channel (bot must be an admin)
- Your Telegram user ID as `ADMIN_TELEGRAM_ID`

## Quick Start

### 1. Clone & configure

```bash
git clone <repo-url> && cd fs-telegram-bot
cp .env.example .env
```

Edit `.env` with `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, and `ADMIN_TELEGRAM_ID` (all required).

### 2. Run with Docker (recommended)

On Linux Engine, ensure bind-mounted dirs are writable by the container user (`appuser`, typically UID 1000):

```bash
mkdir -p data logs
sudo chown -R 1000:1000 data logs   # Linux Engine only; Docker Desktop/Windows usually fine
docker compose up --build -d
```

### 3. Run locally (development)

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
# database.path is data/notices.db relative to the project root
PYTHONPATH=. python -m src.main
```

## Environment Variables

Startup fails without all three Telegram credentials (`src/config.py` `validate_env()`).

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from BotFather |
| `TELEGRAM_CHANNEL_ID` | Yes | Target channel ID (e.g. `@channel` or `-1001234567890`) |
| `ADMIN_TELEGRAM_ID` | Yes | Your numeric Telegram user ID (commands + ops DMs) |
| `LOG_LEVEL` | No | `INFO` (default), `DEBUG`, `WARNING` |
| `TARGET_URL` | No | Fallback if `poll.targets` is missing from YAML |

Poll intervals and target URLs come from `config/settings.yaml`. Retry settings in that YAML drive the tenacity decorator.

## Commands (admin only)

Send these in a private chat with the bot:

| Command | Description |
|---------|-------------|
| `/start` | Subscribe the current chat to announcements |
| `/stop` | Unsubscribe the current chat |
| `/status` | Show total notice count and active department count |
| `/departments` | List all departments with enable/disable status |
| `/subscribe` | Show toggle buttons for departments |
| `/subscribe Computer Science` | Enable a department (English label match) |
| `/unsubscribe Mathematics` | Disable a department |

## Project Structure

```
fs-telegram-bot/
├── src/
│   ├── main.py              # Entry point – scheduler orchestration
│   ├── scraper.py           # httpx + lxml page scraper (7 targets)
│   ├── broadcaster.py       # Telegram messaging with retry logic
│   ├── commands.py          # Telegram command handler (getUpdates)
│   ├── database.py          # SQLite (notices, subscriptions, settings)
│   ├── config.py            # YAML + env config loader
│   ├── heartbeat.py         # Periodic health-check to admin DM
│   └── utils.py             # Date extraction, hashing, HTML formatting
├── config/
│   ├── selectors.json       # CSS selectors for the target site
│   └── settings.yaml        # Targets, intervals, DB paths
├── docs/
│   └── RESEARCH-ISSUES.md   # Cited bug list (F01–F22)
├── tests/
│   └── fixtures/            # Saved HTML for parser tests
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── PLAN.md
└── README.md
```

## License

MIT
