import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils import split_text

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class Broadcaster:
    def __init__(self, token, channel_id, settings):
        self.token = token
        self.channel_id = channel_id
        self.max_length = settings["telegram"]["message_max_length"]
        self.retry_settings = settings["retry"]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
    )
    def _post_message(self, text):
        url = TELEGRAM_API.format(token=self.token)
        payload = {
            "chat_id": self.channel_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    def send(self, text):
        parts = split_text(text, self.max_length)
        for i, part in enumerate(parts):
            try:
                import time
                if i > 0:
                    time.sleep(3)
                self._post_message(part)
                logger.info("Sent message part %d/%d", i + 1, len(parts))
            except Exception as e:
                logger.error("Failed to send message part %d/%d: %s", i + 1, len(parts), e)

    def send_notice(self, title, url, date=""):
        from src.utils import format_notice

        text = format_notice(title, url, date)
        self.send(text)
