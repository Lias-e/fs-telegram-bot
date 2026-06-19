import logging
import logging.handlers
import os
import signal
import sys
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.broadcaster import Broadcaster
from src.config import BASE_DIR, get_env, load_selectors, load_settings, validate_env
from src.database import Database
from src.heartbeat import Heartbeat
from src.scraper import Scraper
from src.utils import sha256_hash

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


def poll_job(scraper, db, broadcaster, settings):
    url = get_env("TARGET_URL", "https://fsciences.univ-setif.dz")
    try:
        notices = scraper.scrape(url)
    except Exception as e:
        logger.error("Poll job failed: %s", e)
        return 30

    new_count = 0
    for notice in notices:
        hash_digest = sha256_hash(notice["url"] + notice["title"])
        if db.is_duplicate(hash_digest):
            continue
        notice_id = hash_digest[:16]
        db.insert_notice(notice_id, notice["url"], notice["title"], hash_digest)
        broadcaster.send_notice(notice["title"], notice["url"], notice["date"])
        new_count += 1

    logger.info("Poll complete: %d new notices found", new_count)

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


def signal_handler(signum, frame):
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

    url = get_env("TARGET_URL", "https://fsciences.univ-setif.dz")
    try:
        sample = scraper.scrape(url)
        if not sample:
            logger.warning("Selector validation: zero notices found on startup")
            broadcaster.send("⚠️ *Selector Validation Warning*\n\nZero notices found on startup. The site structure may have changed – check `config/selectors.json`.")
    except Exception as e:
        logger.warning("Selector validation failed on startup: %s", e)

    _scheduler = BackgroundScheduler()

    def run_poll():
        interval = poll_job(scraper, _db, broadcaster, settings)
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

    try:
        from time import sleep

        while True:
            sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    main()
