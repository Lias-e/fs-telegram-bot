"""One-time cleanup: notify every private-chat subscriber that private chats
are no longer supported, then remove them from the database so the poller
stops sending them notices.

Run manually from the project root:

    python -m scripts.purge_private_subscribers

The script is idempotent — running it again simply finds no private chats.
"""

import logging
import sys
import time

import httpx

from src.config import get_env, load_settings
from src.database import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3

NOTICE = (
    "⚠️ <b>Private chats are no longer supported.</b>\n\n"
    "This bot no longer sends announcements in private chats.\n\n"
    "📢 Please subscribe to the main channel instead:\n{channel_url}"
)


def send_notice(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.warning(
                "Send to %s failed (attempt %d/%d): %s", chat_id, attempt, MAX_ATTEMPTS, e
            )
            if attempt < MAX_ATTEMPTS:
                time.sleep(2**attempt)
    return False


def main():
    settings = load_settings()
    token = (get_env("TELEGRAM_BOT_TOKEN") or "").strip()
    channel_url = (get_env("TELEGRAM_CHANNEL_URL") or "").strip()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set")
        sys.exit(1)
    if not channel_url:
        logger.error("TELEGRAM_CHANNEL_URL is not set (expected e.g. https://t.me/Baz_fs)")
        sys.exit(1)

    db = Database(settings["database"]["path"])
    subs = db.get_subscriptions()
    # Private chats have positive (all-digit) IDs; groups/channels are negative.
    private = [s for s in subs if str(s["chat_id"]).isdigit()]

    if not private:
        logger.info("No private-chat subscribers found — nothing to do")
        return

    logger.info("Found %d private-chat subscriber(s) to notify and remove", len(private))
    text = NOTICE.format(channel_url=channel_url)

    notified = 0
    failed = []
    for sub in private:
        chat_id = sub["chat_id"]
        title = sub.get("chat_title") or "(no title)"
        if send_notice(token, chat_id, text):
            notified += 1
        else:
            failed.append(chat_id)

        db.remove_subscription(chat_id)
        db.remove_chat_target_settings(chat_id)
        logger.info("Removed private-chat subscriber %s (%s)", chat_id, title)

    logger.info(
        "Done: %d notified, %d failed to send, %d removed from %d found",
        notified,
        len(failed),
        len(private),
        len(private),
    )
    if failed:
        logger.info("Send failures (still removed): %s", ", ".join(failed))


if __name__ == "__main__":
    main()
