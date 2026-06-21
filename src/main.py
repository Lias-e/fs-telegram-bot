import logging
import logging.handlers
import os
import signal
import sys
import threading
import time
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.broadcaster import Broadcaster
from src.commands import CommandHandler
from src.config import BASE_DIR, get_env, load_selectors, load_settings, validate_env
from src.database import Database
from src.heartbeat import Heartbeat
from src.scraper import Scraper
from src.utils import extract_date, format_notice_with_seen, sha256_hash

logger = logging.getLogger(__name__)

_browser = None
_db = None
_scheduler = None


def setup_logging(settings):
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log_cfg = settings["logging"]
    formatter = logging.Formatter(log_cfg["format"])

    root = logging.getLogger()
    root.setLevel(get_env("LOG_LEVEL", "INFO"))

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    root.addHandler(stream)

    rotator = logging.handlers.RotatingFileHandler(
        str(log_dir / "app.log"),
        maxBytes=log_cfg["max_bytes"],
        backupCount=log_cfg["backup_count"],
    )
    rotator.setFormatter(formatter)
    root.addHandler(rotator)


def init_browser(settings):
    from playwright.sync_api import sync_playwright

    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    logger.info("Browser launched")
    return p, browser


def poll_job(db, broadcaster, settings, selectors):
    all_targets = settings["poll"].get("targets", [get_env("TARGET_URL", "https://fsciences.univ-setif.dz")])
    targets = db.get_enabled_targets(all_targets)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            scraper = Scraper(browser, selectors, settings)
            notices = scraper.scrape_all(targets)
    except Exception as e:
        logger.error("Poll job failed: %s", e)
        return 30

    subs = db.get_subscriptions()
    chat_ids = [s["chat_id"] for s in subs]
    default_chat = get_env("TELEGRAM_CHANNEL_ID")
    if default_chat and default_chat not in chat_ids:
        chat_ids.insert(0, default_chat)

    new_count = 0
    dup_count = 0
    for notice in notices:
        url = notice["url"]
        if db.is_duplicate(url):
            dup_count += 1
            continue
        hash_digest = sha256_hash(url)
        db.insert_notice(url, notice["title"], hash_digest)
        date = extract_date(notice["title"] + " " + notice["date"])
        text = format_notice_with_seen(notice["title"], notice["url"], date)
        broadcaster.send(text, chat_ids=chat_ids)
        new_count += 1
        if new_count > 0:
            time.sleep(3)

    logger.info("Poll complete: %d new, %d duplicates across %d chats", new_count, dup_count, len(chat_ids))

    if new_count >= settings["poll"]["fast_trigger_count"]:
        return settings["poll"]["fast_interval_minutes"]
    return settings["poll"]["default_interval_minutes"]


def heartbeat_job(heartbeat):
    heartbeat.send()


def backup_job(db, settings):
    db.backup(
        settings["database"]["backup_dir"],
        settings["database"]["backup_retention_days"],
    )


_signal_caught = False


def signal_handler(signum, frame):
    global _signal_caught
    if _signal_caught:
        return
    _signal_caught = True
    logger.info("Received signal %s, shutting down...", signum)
    if _scheduler:
        _scheduler.shutdown(wait=False)
    if _browser:
        _browser[1].close()
        _browser[0].stop()
    if _db:
        _db.close()
    sys.exit(0)


def main():
    global _browser, _db, _scheduler

    validate_env()
    settings = load_settings()
    selectors = load_selectors()
    setup_logging(settings)

    db_path = settings["database"]["path"]
    _db = Database(db_path)

    _browser = init_browser(settings)
    browser = _browser[1]

    scraper = Scraper(browser, selectors, settings)
    broadcaster = Broadcaster(
        get_env("TELEGRAM_BOT_TOKEN"),
        get_env("TELEGRAM_CHANNEL_ID"),
        settings,
    )
    heartbeat = Heartbeat(broadcaster, _db)

    targets = settings["poll"].get("targets", [get_env("TARGET_URL", "https://fsciences.univ-setif.dz")])

    try:
        sample = scraper.scrape_all(targets)
        if not sample:
            logger.warning("Selector validation: zero notices found on startup")
            broadcaster.send("⚠️ *Selector Validation Warning*\n\nZero notices found on startup. The site structure may have changed – check `config/selectors.json`.")
    except Exception as e:
        logger.warning("Selector validation failed on startup: %s", e)

    cmd_handler = CommandHandler(
        get_env("TELEGRAM_BOT_TOKEN"), _db, targets,
        admin_id=get_env("ADMIN_TELEGRAM_ID", None),
    )
    cmd_thread = threading.Thread(target=cmd_handler.run_forever, daemon=True)
    cmd_thread.start()

    _scheduler = BackgroundScheduler()

    def run_poll():
        interval = poll_job(_db, broadcaster, settings, selectors)
        _scheduler.reschedule_job(
            "poll",
            trigger=IntervalTrigger(minutes=interval),
        )

    _scheduler.add_job(
        run_poll,
        IntervalTrigger(minutes=settings["poll"]["default_interval_minutes"]),
        id="poll",
        replace_existing=True,
    )

    _scheduler.add_job(
        heartbeat_job,
        IntervalTrigger(hours=settings["heartbeat"]["interval_hours"]),
        args=[heartbeat],
        id="heartbeat",
        replace_existing=True,
    )

    _scheduler.add_job(
        backup_job,
        IntervalTrigger(hours=24),
        args=[_db, settings],
        id="backup",
        replace_existing=True,
    )

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    _scheduler.start()
    logger.info("Bot started. Polling every %d min.", settings["poll"]["default_interval_minutes"])

    run_poll()

    # Keep main thread alive — daemon threads (scheduler, command handler)
    # would be killed on exit otherwise, causing the container to restart
    threading.Event().wait()


if __name__ == "__main__":
    main()
