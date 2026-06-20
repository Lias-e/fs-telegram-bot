# University Broadcaster Telegram Bot

Autonomous pipeline that polls the **University of Setif 1 – Faculty of Sciences** website (main page + 6 department sub-pages) for new administrative notices and broadcasts them instantly to a Telegram channel with duplicate detection and department-level filtering.

## Features

- **Multi-target monitoring** – scrapes the main page + 6 departments (CS, Math, Physics, Chemistry, MI, SM)
- **Adaptive polling** – checks every 5 min if new notices were found, otherwise every 30 min
- **Duplicate prevention** – SQLite database with SHA256 hashing of `url + title`
- **Multi-chat broadcasting** – sends to the default channel + all subscribed chats/groups
- **Admin-only commands** – only the configured admin user can control the bot
- **Department filtering** – enable/disable individual departments via `/subscribe` / `/unsubscribe`
- **JS-ready parsing** – uses Playwright + lxml to handle dynamic content
- **Resilient** – health checks, file rotation logging, dynamic selector config, tenacity retry
- **Zero cost** – designed for self-hosting on a local Linux server

## Architecture

```
[University Website (7 URLs)]
         ↓
[Playwright Scraper]  →  lxml parsing →  extract date + title + link
         ↓
[SQLite State]
  ├─ notices table (SHA256 dedup)
  ├─ subscriptions table (chat IDs)
  └─ settings table (disabled departments)
         ↓
[httpx + Telegram API]  →  send to all subscribed chats (3s delay between)
         ↑
[Command Handler]  ←  getUpdates polling every 2s
```

## Prerequisites

- Python 3.10+
- Docker & Docker Compose (recommended for deployment)
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- A public Telegram channel

## Quick Start

### 1. Clone & configure

```bash
git clone <repo-url> && cd fs-telegram-bot
cp .env.example .env
```

Edit `.env` with your Telegram credentials.

### 2. Run with Docker (recommended)

```bash
docker compose up --build -d
```

### 3. Run locally (development)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
PYTHONPATH=/path/to/project python -m src.main
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from BotFather |
| `TELEGRAM_CHANNEL_ID` | Yes | Target channel ID (e.g. `@channel` or `-1001234567890`) |
| `ADMIN_TELEGRAM_ID` | Yes | Your Telegram user ID (all commands restricted to this ID) |
| `LOG_LEVEL` | No | `INFO` (default), `DEBUG`, `WARNING` |

## Commands (admin only)

Send these in a private chat with the bot:

| Command | Description |
|---------|-------------|
| `/start` | Subscribe the current chat to announcements |
| `/stop` | Unsubscribe the current chat |
| `/status` | Show total notice count and active department count |
| `/departments` | List all departments with enable/disable status |
| `/subscribe <name>` | Enable a department (e.g. `/subscribe Informatique`) |
| `/unsubscribe <name>` | Disable a department (e.g. `/unsubscribe Maths`) |

## Project Structure

```
fs-telegram-bot/
├── src/
│   ├── main.py              # Entry point – scheduler orchestration
│   ├── scraper.py           # Playwright-based page scraper (7 targets)
│   ├── broadcaster.py       # Telegram messaging with retry logic
│   ├── commands.py          # Telegram command handler (getUpdates polling)
│   ├── database.py          # SQLite operations (notices, subscriptions, settings)
│   ├── config.py            # YAML + env config loader
│   ├── heartbeat.py         # Periodic health-check reporter
│   └── utils.py             # Date extraction, hashing, formatting
├── config/
│   ├── selectors.json       # CSS selectors for the target site
│   └── settings.yaml        # Global application settings (target URLs, intervals)
├── Dockerfile               # Multi-stage build with Playwright
├── docker-compose.yml       # Service orchestration
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
└── README.md
```

## License

MIT
