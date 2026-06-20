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
        self.retry_settings = settings["retry"]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
    )
    def _post_message(self, text, chat_id):
        url = TELEGRAM_API.format(token=self.token)
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    def _send_to_chat(self, text, chat_id):
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

    def send(self, text, chat_ids=None):
        if chat_ids is None:
            chat_ids = [self.default_chat_id]
        for chat_id in chat_ids:
            self._send_to_chat(text, chat_id)

    def send_notice(self, title, url, date="", chat_ids=None):
        from src.utils import format_notice

        text = format_notice(title, url, date)
        self.send(text, chat_ids)
