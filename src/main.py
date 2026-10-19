import logging
import logging.handlers
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.broadcaster import Broadcaster, PHOTO_CAPTION_LIMIT
from src.commands import CommandHandler
from src.config import BASE_DIR, get_env, load_selectors, load_settings, validate_env
from src.database import Database
from src.heartbeat import Heartbeat
from src.scraper import MAX_ATTACHMENTS_PER_NOTICE, Scraper
from src.utils import extract_date, format_notice_with_seen, sha256_hash

logger = logging.getLogger(__name__)

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


def touch_last_poll(settings):
    path = Path(settings["database"]["path"]).parent / "last_poll"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(datetime.now().isoformat(), encoding="utf-8")


def poll_job(db, broadcaster, settings, selectors):
    all_targets = settings["poll"].get("targets", [get_env("TARGET_URL", "https://fsciences.univ-setif.dz")])
    targets = db.get_enabled_targets(all_targets)
    try:
        scraper = Scraper(selectors, settings)
        notices = scraper.scrape_all(targets)
    except Exception as e:
        logger.error("Poll job failed: %s", e)
        return settings["poll"]["default_interval_minutes"]

    # Deduplicate by URL across targets (same notice can appear on multiple pages).
    # When a notice appears both on the faculty homepage and a department page,
    # prefer the department-tagged copy so the announcement gets its hashtag.
    unique = {}
    for notice in notices:
        known = unique.get(notice["url"])
        if (
            known is None
            or known.get("department") == "General"
            and notice.get("department") not in (None, "General")
        ):
            unique[notice["url"]] = notice
    notices = list(unique.values())

    # F02: seed on empty DB — insert all, send nothing
    if db.count() == 0:
        seeded = 0
        for notice in notices:
            hash_digest = sha256_hash(notice["url"])
            if db.insert_notice(notice["url"], notice["title"], hash_digest):
                seeded += 1
        logger.info("Seeded empty DB with %d notices (no broadcast)", seeded)
        touch_last_poll(settings)
        return settings["poll"]["default_interval_minutes"]

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
        detail = None
        try:
            detail = scraper.fetch_notice_details(url)
        except Exception as e:
            logger.warning("Notice detail fetch failed for %s: %s", url, e)
        title = notice["title"]
        if detail and detail["title"]:
            title = detail["title"]
        body_subtitle = (detail or {}).get("subtitle", "")
        body_text = (detail or {}).get("body", "")
        date = extract_date(" ".join(
            part for part in (title, body_subtitle, body_text, notice["date"]) if part
        ))
        text = format_notice_with_seen(title, url, date, department=notice.get("department", ""))
        # If there is an attachment and the caption fits Telegram's 1024-char
        # limit, put the whole message on the file itself instead of sending a
        # separate text message.
        attachments = (detail or {}).get("attachments", [])[:MAX_ATTACHMENTS_PER_NOTICE]
        if attachments and len(text) <= PHOTO_CAPTION_LIMIT:
            path = scraper.download_attachment(attachments[0], "data/attachments")
            if path is not None:
                ok = broadcaster.send_file(
                    str(path), attachments[0]["kind"], caption=text, chat_ids=chat_ids
                )
                Path(path).unlink(missing_ok=True)
                for attachment in attachments[1:]:
                    p = scraper.download_attachment(attachment, "data/attachments")
                    if p is None:
                        continue
                    broadcaster.send_file(str(p), attachment["kind"], caption=title, chat_ids=chat_ids)
                    Path(p).unlink(missing_ok=True)
                    time.sleep(3)
            else:
                ok = broadcaster.send(text, chat_ids=chat_ids)
                for attachment in attachments:
                    p = scraper.download_attachment(attachment, "data/attachments")
                    if p is None:
                        continue
                    broadcaster.send_file(str(p), attachment["kind"], caption=title, chat_ids=chat_ids)
                    Path(p).unlink(missing_ok=True)
                    time.sleep(3)
        else:
            ok = broadcaster.send(text, chat_ids=chat_ids)
            for attachment in attachments:
                p = scraper.download_attachment(attachment, "data/attachments")
                if p is None:
                    continue
                logger.info("Sending attachment %s for %s", attachment["filename"], url)
                broadcaster.send_file(str(p), attachment["kind"], caption=title, chat_ids=chat_ids)
                Path(p).unlink(missing_ok=True)
                time.sleep(3)
        # F01: send first; record only after successful channel delivery
        if ok:
            hash_digest = sha256_hash(url)
            db.insert_notice(url, title, hash_digest)
            new_count += 1
            time.sleep(3)
        else:
            logger.error("Send failed for %s — not recording as seen", url)

    logger.info("Poll complete: %d new, %d duplicates across %d chats", new_count, dup_count, len(chat_ids))
    touch_last_poll(settings)

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
    if _db:
        _db.close()
    sys.exit(0)


def main():
    global _db, _scheduler

    validate_env()
    settings = load_settings()
    selectors = load_selectors()
    setup_logging(settings)

    admin_id = get_env("ADMIN_TELEGRAM_ID")
    db_path = settings["database"]["path"]
    _db = Database(db_path)

    scraper = Scraper(selectors, settings)
    broadcaster = Broadcaster(
        get_env("TELEGRAM_BOT_TOKEN"),
        get_env("TELEGRAM_CHANNEL_ID"),
        settings,
    )
    heartbeat = Heartbeat(broadcaster, _db, admin_id)

    targets = settings["poll"].get("targets", [get_env("TARGET_URL", "https://fsciences.univ-setif.dz")])

    try:
        sample = scraper.scrape_all(targets)
        if not sample:
            logger.warning("Selector validation: zero notices found on startup")
            broadcaster.send_to_admin(
                "⚠️ <b>Selector Validation Warning</b>\n\n"
                "Zero notices found on startup. The site structure may have changed – "
                "check <code>config/selectors.json</code>.",
                admin_id,
            )
    except Exception as e:
        logger.warning("Selector validation failed on startup: %s", e)

    cmd_handler = CommandHandler(
        get_env("TELEGRAM_BOT_TOKEN"), _db, targets,
        admin_id=admin_id,
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
        next_run_time=datetime.now(),
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

    # Keep main thread alive — daemon threads (scheduler, command handler)
    # would be killed on exit otherwise, causing the container to restart
    threading.Event().wait()


if __name__ == "__main__":
    main()
