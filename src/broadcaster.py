import logging
import time

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils import split_text

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class Broadcaster:
    def __init__(self, token, channel_id, settings):
        self.token = token
        self.default_chat_id = channel_id
        self.max_length = settings["telegram"]["message_max_length"]
        retry_cfg = settings.get("retry", {})
        self._max_attempts = retry_cfg.get("max_attempts", 3)
        self._backoff_multiplier = retry_cfg.get("backoff_multiplier", 2)
        self._backoff_min = retry_cfg.get("backoff_min_seconds", 4)
        self._backoff_max = retry_cfg.get("backoff_max_seconds", 60)

    def _post_message(self, text, chat_id):
        @retry(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(
                multiplier=self._backoff_multiplier,
                min=self._backoff_min,
                max=self._backoff_max,
            ),
            reraise=True,
        )
        def _do_post():
            url = TELEGRAM_API.format(token=self.token)
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            }
            with httpx.Client(timeout=30) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()

        return _do_post()

    def _send_to_chat(self, text, chat_id):
        """Send all parts to one chat. Returns True if every part succeeded."""
        parts = split_text(text, self.max_length)
        for i, part in enumerate(parts):
            try:
                if i > 0:
                    time.sleep(3)
                self._post_message(part, chat_id)
                if chat_id == self.default_chat_id:
                    logger.info("Sent message part %d/%d to default channel", i + 1, len(parts))
            except Exception as e:
                logger.error("Failed to send to %s part %d/%d: %s", chat_id, i + 1, len(parts), e)
                return False
        return True

    def send(self, text, chat_ids=None):
        """
        Send text to chats. Returns True if the default/primary chat succeeded.
        When chat_ids is provided, success is judged by TELEGRAM_CHANNEL_ID
        (or the first id if the default is not in the list). Subscriber failures
        are logged but do not fail the overall send for recording purposes.
        """
        if chat_ids is None:
            chat_ids = [self.default_chat_id]

        primary = self.default_chat_id if self.default_chat_id in chat_ids else chat_ids[0]
        primary_ok = False
        for chat_id in chat_ids:
            ok = self._send_to_chat(text, chat_id)
            if chat_id == primary:
                primary_ok = ok
        return primary_ok

    def send_to_admin(self, text, admin_id):
        if not admin_id:
            logger.warning("No admin id; skipping ops message")
            return False
        return self._send_to_chat(text, str(admin_id))

    def send_notice(self, title, url, date="", chat_ids=None):
        from src.utils import format_notice

        text = format_notice(title, url, date)
        return self.send(text, chat_ids)
