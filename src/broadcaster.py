import logging
import time
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils import split_text

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"
PHOTO_CAPTION_LIMIT = 1024
DOCUMENT_CAPTION_LIMIT = 1024


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

    @staticmethod
    def _normalize_targets(targets):
        """Accept [(chat_id, thread_id|None), ...] or plain chat ids."""
        out = []
        for entry in targets:
            if isinstance(entry, tuple):
                out.append(entry)
            else:
                out.append((entry, None))
        return out

    def _post_message(self, text, chat_id, thread_id=None):
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
            url = TELEGRAM_API.format(token=self.token) + "/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            }
            if thread_id:
                payload["message_thread_id"] = thread_id
            with httpx.Client(timeout=30) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()

        return _do_post()

    def _post_file(self, file_path, kind, caption, chat_id, thread_id=None):
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
            url = TELEGRAM_API.format(token=self.token) + (
                "/sendPhoto" if kind == "photo" else "/sendDocument"
            )
            method = "photo" if kind == "photo" else "document"
            cap = (caption or "")[: PHOTO_CAPTION_LIMIT if kind == "photo" else DOCUMENT_CAPTION_LIMIT]
            data = {"chat_id": chat_id, "caption": cap, "parse_mode": "HTML"}
            if thread_id:
                data["message_thread_id"] = thread_id
            with httpx.Client(timeout=120) as client:
                with open(file_path, "rb") as fh:
                    resp = client.post(
                        url,
                        data=data,
                        files={method: (Path(file_path).name, fh)},
                    )
                resp.raise_for_status()
                return resp.json()

        return _do_post()

    def send_file(self, file_path, kind, caption="", chat_ids=None):
        """Send a local file (photo or document) to the given target chats.
        chat_ids entries may be (chat_id, message_thread_id) tuples."""
        entries = self._normalize_targets(chat_ids if chat_ids is not None else [self.default_chat_id])
        ok_all = True
        for chat_id, thread_id in entries:
            try:
                self._post_file(file_path, kind, caption, chat_id, thread_id)
            except Exception as e:
                logger.error("Failed to send file to %s: %s", chat_id, e)
                ok_all = False
        return ok_all

    def _send_to_chat(self, text, chat_id, thread_id=None):
        """Send all parts to one chat. Returns True if every part succeeded."""
        parts = split_text(text, self.max_length)
        for i, part in enumerate(parts):
            try:
                if i > 0:
                    time.sleep(3)
                self._post_message(part, chat_id, thread_id)
                if chat_id == self.default_chat_id:
                    logger.info("Sent message part %d/%d to default channel", i + 1, len(parts))
            except Exception as e:
                logger.error("Failed to send to %s part %d/%d: %s", chat_id, i + 1, len(parts), e)
                return False
        return True

    def send(self, text, chat_ids=None):
        """
        Send text to chats. Entries may be (chat_id, message_thread_id) tuples
        for group topics. Success is judged by TELEGRAM_CHANNEL_ID.
        Subscriber failures are logged but do not fail the overall send.
        """
        entries = self._normalize_targets(chat_ids if chat_ids is not None else [self.default_chat_id])
        primary_chat = self.default_chat_id if self.default_chat_id in [e[0] for e in entries] else entries[0][0]
        primary_ok = False
        for chat_id, thread_id in entries:
            ok = self._send_to_chat(text, chat_id, thread_id)
            if chat_id == primary_chat:
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
