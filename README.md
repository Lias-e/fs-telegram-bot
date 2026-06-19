# University Broadcaster Telegram Bot

Autonomous pipeline that polls the **University of Setif 1 – Faculty of Sciences** website for new administrative notices (PDFs, announcements), filters duplicates using SHA256 content hashing, and broadcasts them instantly to a public Telegram channel.

## Features

- **Autonomous monitoring** – polls `fsciences.univ-setif.dz` every 30 minutes (adaptive to 5 min for recent updates)
- **Duplicate prevention** – SQLite database with SHA256 content hashing
- **Instant broadcasting** – pushes to Telegram channel with retry + exponential backoff
- **JS-ready parsing** – uses Playwright + lxml to handle dynamic content
- **Zero cost** – designed for self-hosting on a local DIY Linux server
- **Resilient** – health checks, file rotation logging, dynamic selector config

## Architecture

```
[University Website] → [Playwright Scraper] → [SQLite State] → [httpx + Telegram API] → [Student Channel]
         ↑                    ↑                    ↑                    ↑
    (30 min adaptive)   (JS-ready parsing)   (hash + timestamps)   (retry 3x)
```

### Key Components

| Component | Choice |
|-----------|--------|
| Parsing | Playwright + lxml |
| Storage | SQLite (notices table with SHA256 hashes) |
| Scheduler | APScheduler |
| HTTP | httpx (async-ready, built-in retry) |
| Config | YAML + environment variables |

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

Edit `.env` with your Telegram credentials and target URL.

### 2. Run with Docker (recommended)

```bash
docker compose up --build -d
```

### 3. Run locally (development)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python src/main.py
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from BotFather |
| `TELEGRAM_CHANNEL_ID` | Yes | Target channel ID (e.g. `@channel` or `-1001234567890`) |
| `TARGET_URL` | No | Defaults to `https://fsciences.univ-setif.dz` |
| `LOG_LEVEL` | No | `INFO` (default), `DEBUG`, `WARNING` |
| `POLL_INTERVAL` | No | Default polling interval in minutes (default: `30`) |

## Project Structure

```
fs-telegram-bot/
├── src/
│   ├── main.py              # Entry point – scheduler orchestration
│   ├── scraper.py           # Playwright-based page scraper
│   ├── broadcaster.py       # Telegram messaging with retry logic
│   ├── database.py          # SQLite operations (init, insert, lookup)
│   ├── config.py            # YAML + env config loader
│   ├── heartbeat.py         # Periodic health-check reporter
│   └── utils.py             # Helpers (text splitting, hashing)
├── config/
│   ├── selectors.json       # CSS/XPath selectors for target site
│   └── settings.yaml        # Global application settings
├── Dockerfile               # Multi-stage build
├── docker-compose.yml       # Service orchestration
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
└── README.md
```

## License

MIT
