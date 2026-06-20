import logging
import time

import httpx

logger = logging.getLogger(__name__)

DEPARTMENT_LABELS = {
    "https://fsciences.univ-setif.dz": "Faculty (main)",
    "https://fsciences.univ-setif.dz/sites_departements/informatique": "Computer Science",
    "https://fsciences.univ-setif.dz/sites_departements/maths": "Mathematics",
    "https://fsciences.univ-setif.dz/sites_departements/physique": "Physics",
    "https://fsciences.univ-setif.dz/sites_departements/chimie": "Chemistry",
    "https://fsciences.univ-setif.dz/sites_departements/mi": "MI (Math-Info)",
    "https://fsciences.univ-setif.dz/sites_departements/sm": "SM (Material Sci.)",
}


class CommandHandler:
    def __init__(self, token, db, targets, admin_id=None):
        self.token = token
        self.db = db
        self.targets = targets
        self.admin_id = admin_id
        self._offset = 0

    def _send(self, chat_id, text):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
        except Exception as e:
            logger.error("Failed to reply to %s: %s", chat_id, e)

    def _is_admin(self, user_id):
        return self.admin_id is not None and str(user_id) == str(self.admin_id)

    def _handle(self, msg):
        chat_id = str(msg.get("chat", {}).get("id", ""))
        user_id = msg.get("from", {}).get("id")
        text = (msg.get("text") or "").strip()
        if not text or not chat_id:
            return

        if text == "/start":
            self.db.add_subscription(chat_id, msg.get("chat", {}).get("title", ""))
            self._send(chat_id, "✅ This chat is now subscribed to faculty announcements.\n\nUse /stop to unsubscribe.")
            logger.info("Subscribed chat %s", chat_id)
            return

        if text == "/stop":
            self.db.remove_subscription(chat_id)
            self._send(chat_id, "❌ Unsubscribed from announcements.")
            logger.info("Unsubscribed chat %s", chat_id)
            return

        if text == "/status":
            count = self.db.count()
            depts = self.db.get_enabled_targets(self.targets)
            lines = [
                f"📊 *Total notices:* {count}",
                f"📡 *Active departments:* {len(depts)}/{len(self.targets)}",
            ]
            self._send(chat_id, "\n".join(lines))
            return

        if text.startswith("/departments") and self._is_admin(user_id):
            disabled_raw = self.db.get_setting("disabled_targets", "")
            disabled = set(disabled_raw.split(",")) if disabled_raw else set()
            lines = ["*Departments:*"]
            for url, label in DEPARTMENT_LABELS.items():
                if url in self.targets:
                    status = "❌" if url in disabled else "✅"
                    lines.append(f"{status} {label}")
            lines.append("\nUse `/subscribe <name>` or `/unsubscribe <name>`")
            self._send(chat_id, "\n".join(lines))
            return

        if text.startswith("/subscribe") and self._is_admin(user_id):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                self._send(chat_id, "Usage: `/subscribe Computer Science`")
                return
            name = parts[1].lower()
            matched = None
            for url, label in DEPARTMENT_LABELS.items():
                if name in label.lower() and url in self.targets:
                    matched = url
                    break
            if not matched:
                self._send(chat_id, f"Department '{parts[1]}' not found. Use /departments to see available ones.")
                return
            disabled_raw = self.db.get_setting("disabled_targets", "")
            disabled = set(disabled_raw.split(",")) if disabled_raw else set()
            disabled.discard(matched)
            self.db.set_setting("disabled_targets", ",".join(sorted(disabled)))
            self._send(chat_id, f"✅ Enabled: {DEPARTMENT_LABELS[matched]}")
            return

        if text.startswith("/unsubscribe") and self._is_admin(user_id):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                self._send(chat_id, "Usage: `/unsubscribe Computer Science`")
                return
            name = parts[1].lower()
            matched = None
            for url, label in DEPARTMENT_LABELS.items():
                if name in label.lower() and url in self.targets:
                    matched = url
                    break
            if not matched:
                self._send(chat_id, f"Department '{parts[1]}' not found.")
                return
            disabled_raw = self.db.get_setting("disabled_targets", "")
            disabled = set(disabled_raw.split(",")) if disabled_raw else set()
            disabled.add(matched)
            self.db.set_setting("disabled_targets", ",".join(sorted(disabled)))
            self._send(chat_id, f"❌ Disabled: {DEPARTMENT_LABELS[matched]}")
            return

    def poll_once(self):
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        params = {"offset": self._offset, "timeout": 10}
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                for update in data.get("result", []):
                    self._offset = update["update_id"] + 1
                    msg = update.get("message")
                    if msg:
                        self._handle(msg)
        except Exception as e:
            logger.debug("getUpdates poll: %s", e)

    def run_forever(self):
        logger.info("Command handler started")
        while True:
            try:
                self.poll_once()
            except Exception as e:
                logger.error("Command handler error: %s", e)
            time.sleep(2)
