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

REPLY_KEYBOARD = {
    "keyboard": [
        ["/status", "/departments", "/help"],
        ["/subscribe", "/unsubscribe"],
        ["/stop"],
    ],
    "resize_keyboard": True,
}


class CommandHandler:
    def __init__(self, token, db, targets, admin_id=None):
        self.token = token
        self.db = db
        self.targets = targets
        self.admin_id = admin_id
        self._offset = 0

    def _send(self, chat_id, text, reply_markup=None):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
        except Exception as e:
            logger.error("Failed to reply to %s: %s", chat_id, e)

    def _answer_callback(self, callback_id, text, show_alert=False):
        url = f"https://api.telegram.org/bot{self.token}/answerCallbackQuery"
        payload = {"callback_query_id": callback_id, "text": text, "show_alert": show_alert}
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
        except Exception as e:
            logger.error("Failed to answer callback: %s", e)

    def _build_dept_keyboard(self):
        disabled_raw = self.db.get_setting("disabled_targets", "")
        disabled = set(disabled_raw.split(",")) if disabled_raw else set()
        inline_keyboard = []
        for url, label in DEPARTMENT_LABELS.items():
            if url in self.targets:
                status = "✅" if url not in disabled else "❌"
                inline_keyboard.append([{"text": f"{status} {label}", "callback_data": f"dept|{url}"}])
        return {"inline_keyboard": inline_keyboard}

    def _edit_keyboard(self, chat_id, message_id):
        url = f"https://api.telegram.org/bot{self.token}/editMessageReplyMarkup"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": self._build_dept_keyboard(),
        }
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
        except Exception as e:
            logger.error("Failed to edit keyboard: %s", e)

    def _is_admin(self, user_id):
        return self.admin_id is not None and str(user_id) == str(self.admin_id)

    def _handle(self, msg):
        chat_id = str(msg.get("chat", {}).get("id", ""))
        user_id = msg.get("from", {}).get("id")
        text = (msg.get("text") or "").strip()
        if not text or not chat_id:
            return

        if not self._is_admin(user_id):
            return

        if text == "/start":
            self.db.add_subscription(chat_id, msg.get("chat", {}).get("title", ""))
            self._send(
                chat_id,
                "✅ This chat is now subscribed to faculty announcements.",
                reply_markup=REPLY_KEYBOARD,
            )
            logger.info("Subscribed chat %s", chat_id)
            return

        if text == "/stop":
            self.db.remove_subscription(chat_id)
            self._send(chat_id, "❌ Unsubscribed from announcements.", reply_markup={"remove_keyboard": True})
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

        if text == "/help":
            lines = [
                "*Available commands:*",
                "/start — Subscribe this chat",
                "/stop — Unsubscribe this chat",
                "/status — Show stats",
                "/departments — List departments",
                "/subscribe — Toggle departments (buttons)",
                "/unsubscribe <name> — Quick disable a department",
                "/help — This message",
            ]
            self._send(chat_id, "\n".join(lines))
            return

        if text == "/departments":
            disabled_raw = self.db.get_setting("disabled_targets", "")
            disabled = set(disabled_raw.split(",")) if disabled_raw else set()
            lines = ["*Departments:*"]
            for url, label in DEPARTMENT_LABELS.items():
                if url in self.targets:
                    status = "❌" if url in disabled else "✅"
                    lines.append(f"{status} {label}")
            self._send(chat_id, "\n".join(lines))
            return

        if text == "/subscribe":
            self._send(
                chat_id,
                "Tap a department to toggle it on/off:",
                reply_markup=self._build_dept_keyboard(),
            )
            return

        if text.startswith("/subscribe "):
            name = text.split(maxsplit=1)[1].lower()
            matched = None
            for url, label in DEPARTMENT_LABELS.items():
                if name in label.lower() and url in self.targets:
                    matched = url
                    break
            if not matched:
                self._send(chat_id, f"Department not found. Use /subscribe to see buttons.")
                return
            disabled_raw = self.db.get_setting("disabled_targets", "")
            disabled = set(disabled_raw.split(",")) if disabled_raw else set()
            disabled.discard(matched)
            self.db.set_setting("disabled_targets", ",".join(sorted(disabled)))
            self._send(chat_id, f"✅ Enabled: {DEPARTMENT_LABELS[matched]}")
            return

        if text == "/unsubscribe":
            self._send(
                chat_id,
                "Tap a department to toggle it on/off:",
                reply_markup=self._build_dept_keyboard(),
            )
            return

        if text.startswith("/unsubscribe "):
            name = text.split(maxsplit=1)[1].lower()
            matched = None
            for url, label in DEPARTMENT_LABELS.items():
                if name in label.lower() and url in self.targets:
                    matched = url
                    break
            if not matched:
                self._send(chat_id, f"Department not found. Use /subscribe to see buttons.")
                return
            disabled_raw = self.db.get_setting("disabled_targets", "")
            disabled = set(disabled_raw.split(",")) if disabled_raw else set()
            disabled.add(matched)
            self.db.set_setting("disabled_targets", ",".join(sorted(disabled)))
            self._send(chat_id, f"❌ Disabled: {DEPARTMENT_LABELS[matched]}")
            return

    def _handle_callback(self, callback):
        data = callback.get("data", "")
        cb_id = callback.get("id")
        msg = callback.get("message", {})
        chat_id = str(msg.get("chat", {}).get("id", ""))
        user_id = callback.get("from", {}).get("id")
        message_id = msg.get("message_id")

        if not self._is_admin(user_id):
            self._answer_callback(cb_id, "Not authorized", show_alert=True)
            return

        if not data.startswith("dept|"):
            self._answer_callback(cb_id, "Unknown action")
            return

        url = data.replace("dept|", "", 1)
        disabled_raw = self.db.get_setting("disabled_targets", "")
        disabled = set(disabled_raw.split(",")) if disabled_raw else set()
        label = DEPARTMENT_LABELS.get(url, url)

        if url in disabled:
            disabled.discard(url)
            action = "✅ Enabled"
        else:
            disabled.add(url)
            action = "❌ Disabled"

        self.db.set_setting("disabled_targets", ",".join(sorted(disabled)))
        self._answer_callback(cb_id, f"{action}: {label}")

        if chat_id and message_id:
            self._edit_keyboard(chat_id, message_id)

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
                    if "message" in update:
                        self._handle(update["message"])
                    elif "callback_query" in update:
                        self._handle_callback(update["callback_query"])
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
