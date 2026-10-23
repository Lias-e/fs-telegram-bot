import html
import json
import logging
import time

import httpx

logger = logging.getLogger(__name__)

# Short slugs for Telegram callback_data (must stay ≤ 64 bytes with "dept|" prefix)
DEPARTMENT_SLUGS = {
    "main": "https://fsciences.univ-setif.dz",
    "informatique": "https://fsciences.univ-setif.dz/sites_departements/informatique",
    "maths": "https://fsciences.univ-setif.dz/sites_departements/maths",
    "physique": "https://fsciences.univ-setif.dz/sites_departements/physique",
    "chimie": "https://fsciences.univ-setif.dz/sites_departements/chimie",
    "mi": "https://fsciences.univ-setif.dz/sites_departements/mi",
    "sm": "https://fsciences.univ-setif.dz/sites_departements/sm",
}

URL_TO_SLUG = {url: slug for slug, url in DEPARTMENT_SLUGS.items()}

DEPARTMENT_LABELS = {
    "https://fsciences.univ-setif.dz": "Faculty (main)",
    "https://fsciences.univ-setif.dz/sites_departements/informatique": "Computer Science",
    "https://fsciences.univ-setif.dz/sites_departements/maths": "Mathematics",
    "https://fsciences.univ-setif.dz/sites_departements/physique": "Physics",
    "https://fsciences.univ-setif.dz/sites_departements/chimie": "Chemistry",
    "https://fsciences.univ-setif.dz/sites_departements/mi": "MI (Math-Info)",
    "https://fsciences.univ-setif.dz/sites_departements/sm": "SM (Material Sci.)",
}

DISPLAY_CMDS = {
    "/start": "🚀 Start",
    "/stop": "⛔ Stop",
    "/status": "📊 Status",
    "/departments": "📋 Departments",
    "/schedule": "🗓 Timetables",
    "/help": "❓ Help",
    "/subscribe": "✅ Subscribe",
    "/unsubscribe": "❌ Unsubscribe",
    "/bind": "🔗 Bind Topic",
}

DISPLAY_TO_CMD = {v: k for k, v in DISPLAY_CMDS.items()}

REPLY_KEYBOARD = {
    "keyboard": [
        [DISPLAY_CMDS["/status"], DISPLAY_CMDS["/schedule"], DISPLAY_CMDS["/help"]],
        [DISPLAY_CMDS["/subscribe"], DISPLAY_CMDS["/unsubscribe"]],
        [DISPLAY_CMDS["/stop"]],
    ],
    "resize_keyboard": True,
}


MAX_PER_DEPARTMENT = 4
TT_LIST_LIMIT = 6
BIND_PREFIX = "bind"


def _timetable_entries(db):
    """Parsed timetable index from the poll-refreshed cache."""
    raw = db.get_setting("timetable_index", "[]")
    try:
        entries = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return [e for e in entries if isinstance(e, dict) and e.get("url") and e.get("title")]


def _timetable_dept_buttons(db):
    """Inline keyboard: one button per department that has timetable notices."""
    entries = _timetable_entries(db)
    counts = {}
    order = []
    for e in entries:
        dept = e.get("source") or list(DEPARTMENT_LABELS)[0]
        if dept not in DEPARTMENT_LABELS:
            dept = list(DEPARTMENT_LABELS)[0]
        if dept not in counts:
            counts[dept] = 0
            order.append(dept)
        counts[dept] += 1
    if not order:
        return None
    keyboard = []
    for dept in order:
        slug = URL_TO_SLUG.get(dept)
        if not slug:
            continue
        label = f"▼ {DEPARTMENT_LABELS[dept]} ({counts[dept]})"
        keyboard.append([{"text": label, "callback_data": f"ttdept|{slug}"}])
    return {"inline_keyboard": keyboard}


def _timetable_entry_buttons(db, dept_url):
    """Inline keyboard: timetable entries of one department, plus Back."""
    group = [e for e in _timetable_entries(db) if e.get("source") == dept_url]
    # Banner-subtitle heuristic (same dashboard text repeated on every item)
    subs = {(e.get("subtitle") or "").strip() for e in group}
    carry_sub = not (len(group) > 1 and len(subs) == 1 and list(subs)[0] != "")
    keyboard = []
    for e in group[:TT_LIST_LIMIT]:
        notice_id = e["url"].rstrip("/").split("/")[-1]
        label = e["title"][:60]
        keyboard.append([{"text": f"📄 {label}", "callback_data": f"ttsend|{notice_id}"}])
    if group:
        keyboard.append([{"text": "« Departments", "callback_data": "ttback"}])
    return {
        "inline_keyboard": keyboard,
        "count": len(group),
        "carry_subtitles": carry_sub,
    }


class CommandHandler:
    def __init__(self, token, db, targets, admin_id=None, broadcaster=None):
        self.token = token
        self.db = db
        self.targets = targets
        self.admin_id = admin_id
        self.broadcaster = broadcaster
        self._offset = 0
        self._scraper = None

    def _get_scraper(self):
        if self._scraper is None:
            from src.config import load_selectors, load_settings
            from src.scraper import Scraper
            self._scraper = Scraper(load_selectors(), load_settings())
        return self._scraper

    def _send_timetable_file(self, targets_url_or_id, chat_id, thread_id):
        """Look up a timetable notice by id, download its attachments and
        send them (up to 3) as real files into the chat/topic."""
        from src.scraper import MAX_ATTACHMENTS_PER_NOTICE

        if not self.broadcaster:
            self._send(chat_id, "File sending is not configured.", thread_id=thread_id)
            return

        entries = _timetable_entries(self.db)
        entry = next((e for e in entries if e["url"].rstrip("/").endswith(targets_url_or_id)), None)
        if not entry:
            self._send(chat_id, "That timetable entry is no longer available (index refreshed).", thread_id=thread_id)
            return

        scraper = self._get_scraper()
        detail = scraper.fetch_notice_details(entry["url"])
        attachments = (detail or {}).get("attachments", [])[:MAX_ATTACHMENTS_PER_NOTICE]
        if not attachments:
            self._send(
                chat_id,
                f"⚠️ No PDF/image found on <a href=\"{html.escape(entry['url'], quote=True)}\">"
                f"{html.escape(entry['title'])}</a>.",
                thread_id=thread_id,
            )
            return
        import time
        import tempfile
        for attachment in attachments:
            path = scraper.download_attachment(attachment, tempfile.gettempdir() + "/tt_attachments")
            if path is None:
                continue
            caption = f"📄 <b>{html.escape(entry['title'])}</b>"
            if entry.get("subtitle"):
                caption += f"\n📅 {html.escape(entry['subtitle'])}"
            self.broadcaster.send_file(
                str(path), attachment["kind"], caption=caption,
                chat_ids=[(chat_id, thread_id)],
            )
            try:
                import pathlib as _pl
                _pl.Path(path).unlink(missing_ok=True)
            except Exception:
                pass
            time.sleep(3)

    def _send(self, chat_id, text, reply_markup=None, thread_id=None):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if thread_id:
            payload["message_thread_id"] = thread_id
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

    def _build_dept_keyboard(self, chat_id, thread_id=None, for_bind=False):
        """
        Inline keyboard either for a chat's own subscription toggles or,
        for_bind=True, for binding THIS topic to a department.
        """
        bindings = self.db.get_topic_bindings(chat_id) if for_bind else {}
        if for_bind:
            selection = []
        else:
            selection = self.db.get_chat_targets(chat_id)
            if selection is None:
                selection = self._default_enabled()
        enabled = set(selection)
        inline_keyboard = []
        for url, label in DEPARTMENT_LABELS.items():
            if url in self.targets:
                slug = URL_TO_SLUG.get(url)
                if not slug:
                    continue
                if for_bind:
                    bound_thread = next(
                        (t for t, u in bindings.items() if u == url), None
                    )
                    if bound_thread is not None and str(bound_thread) == str(thread_id):
                        marker = "🔗"
                    elif bound_thread is not None:
                        marker = "•"
                    else:
                        marker = "➕"
                    callback_data = f"{BIND_PREFIX}|{thread_id}|{slug}"
                else:
                    marker = "✅" if url in enabled else "❌"
                    callback_data = f"dept|{slug}"
                inline_keyboard.append([{"text": f"{marker} {label}", "callback_data": callback_data}])
        return {"inline_keyboard": inline_keyboard}

    def _default_enabled(self):
        return self.db.default_enabled_targets(self.targets)

    def _user_enabled(self, chat_id):
        """This chat's enabled targets (explicit selection or global default)."""
        selection = self.db.get_chat_targets(chat_id)
        if selection is None:
            return self._default_enabled()
        return selection

    def _toggle_chat_target(self, chat_id, url):
        """Toggle one department for this chat. Returns True if now enabled."""
        selection = self._user_enabled(chat_id)
        if url in selection:
            selection.remove(url)
        else:
            selection.append(url)
        self.db.set_chat_targets(chat_id, selection)
        return url in selection

    def _edit_keyboard(self, chat_id, message_id, for_bind=False, thread_id=None):
        url = f"https://api.telegram.org/bot{self.token}/editMessageReplyMarkup"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": self._build_dept_keyboard(chat_id, thread_id, for_bind),
        }
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
        except Exception as e:
            logger.error("Failed to edit keyboard: %s", e)

    def _is_admin(self, user_id):
        return self.admin_id is not None and str(user_id) == str(self.admin_id)

    def _delete_webhook(self):
        url = f"https://api.telegram.org/bot{self.token}/deleteWebhook"
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(url, json={"drop_pending_updates": False})
                resp.raise_for_status()
                logger.info("deleteWebhook ok")
        except Exception as e:
            logger.error("deleteWebhook failed: %s", e)

    def _handle(self, msg):
        chat = msg.get("chat", {})
        chat_id = str(chat.get("id", ""))
        user_id = msg.get("from", {}).get("id")
        text = (msg.get("text") or "").strip()
        if not text or not chat_id:
            return

        # Remember when a subscribed chat is a forum group — broadcasts then
        # require a bound topic instead of a plain send.
        if chat.get("is_forum"):
            if not self.db.get_setting(f"is_forum:{chat_id}"):
                self.db.set_setting(f"is_forum:{chat_id}", "1")

        if not self._is_admin(user_id):
            # Non-admins can still use subscription commands, but topic
            # binding stays admin-only.
            if text not in DISPLAY_TO_CMD and not text.startswith("/"):
                return

        text = DISPLAY_TO_CMD.get(text, text)

        if text == "/start":
            self.db.add_subscription(chat_id, msg.get("chat", {}).get("title", ""))
            self._send(
                chat_id,
                "✅ This chat is now subscribed to faculty announcements.\n\n"
                "All departments are enabled by default — use /subscribe to "
                "pick only the ones you receive.",
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
            enabled = self._user_enabled(chat_id)
            labels = [
                DEPARTMENT_LABELS[u].split(" (")[0]
                for u in enabled
                if u in DEPARTMENT_LABELS
            ]
            lines = [
                f"📊 <b>Total notices:</b> {count}",
                f"📡 <b>You receive:</b> {len(enabled)}/{len(self.targets)} departments",
            ]
            if labels:
                lines.append(f"🏷 {html.escape(', '.join(labels))}")
            self._send(chat_id, "\n".join(lines))
            return

        if text == "/schedule":
            buttons = _timetable_dept_buttons(self.db)
            if not buttons:
                self._send(
                    chat_id,
                    "🗓 <b>Timetables</b>\n\n"
                    "No timetable announcements found yet. They will appear here as "
                    "soon as the site publishes any.",
                )
                return
            self._send(
                chat_id,
                "🗓 <b>Timetables</b>\n\nPick a department to see its latest timetables:",
                reply_markup=buttons,
            )
            return

        if text == "/bind":
            thread_id = msg.get("message_thread_id")
            if not thread_id:
                self._send(
                    chat_id,
                    "🔗 <b>Bind Topic</b>\n\nOpen a group with Topics enabled, "
                    "then run <code>/bind</code> inside the topic you want to "
                    "link to a department.",
                )
                return
            if not self._is_admin(user_id):
                self._send(chat_id, "Only the admin can bind topics.", thread_id=thread_id)
                return
            self._send(
                chat_id,
                "Tap the department this topic should receive:",
                reply_markup=self._build_dept_keyboard(
                    chat_id, thread_id=str(thread_id), for_bind=True
                ),
                thread_id=thread_id,
            )
            return

        if text == "/help":
            lines = [
                "<b>Commands:</b>",
                f"{DISPLAY_CMDS['/start']} — Subscribe this chat (all departments)",
                f"{DISPLAY_CMDS['/stop']} — Unsubscribe this chat",
                f"{DISPLAY_CMDS['/status']} — Your subscription summary",
                f"{DISPLAY_CMDS['/schedule']} — Timetables browser (fetch PDFs)",
                f"{DISPLAY_CMDS['/departments']} — Your enabled departments",
                f"{DISPLAY_CMDS['/subscribe']} — Pick which departments you receive",
                f"{DISPLAY_CMDS['/unsubscribe']} — Same as /subscribe (toggle off)",
                f"{DISPLAY_CMDS['/bind']} — Admin: link a group topic to a department",
                f"{DISPLAY_CMDS['/help']} — This message",
            ]
            self._send(chat_id, "\n".join(lines))
            return

        if text == "/departments":
            enabled = set(self._user_enabled(chat_id))
            lines = ["<b>Your departments:</b>"]
            for url, label in DEPARTMENT_LABELS.items():
                if url in self.targets:
                    status = "❌" if url not in enabled else "✅"
                    lines.append(f"{status} {html.escape(label)}")
            self._send(chat_id, "\n".join(lines))
            return

        if text == "/subscribe":
            self._send(
                chat_id,
                "Tap a department to toggle it on/off for this chat:",
                reply_markup=self._build_dept_keyboard(chat_id),
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
                self._send(chat_id, "Department not found. Use /subscribe to see buttons.")
                return
            if matched in self._user_enabled(chat_id):
                self._send(chat_id, f"You already receive: {html.escape(DEPARTMENT_LABELS[matched])}")
                return
            self._toggle_chat_target(chat_id, matched)
            self._send(chat_id, f"✅ Enabled for this chat: {html.escape(DEPARTMENT_LABELS[matched])}")
            return

        if text == "/unsubscribe":
            self._send(
                chat_id,
                "Tap a department to toggle it on/off for this chat:",
                reply_markup=self._build_dept_keyboard(chat_id),
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
                self._send(chat_id, "Department not found. Use /subscribe to see buttons.")
                return
            if matched not in self._user_enabled(chat_id):
                self._send(chat_id, f"You don't receive: {html.escape(DEPARTMENT_LABELS[matched])}")
                return
            self._toggle_chat_target(chat_id, matched)
            self._send(chat_id, f"❌ Disabled for this chat: {html.escape(DEPARTMENT_LABELS[matched])}")
            return

    def _edit_text(self, chat_id, message_id, text, inline_keyboard):
        url = f"https://api.telegram.org/bot{self.token}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": inline_keyboard},
        }
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
        except Exception as e:
            logger.error("Failed to edit message %s: %s", message_id, e)

    def _handle_callback(self, callback):
        data = callback.get("data", "")
        cb_id = callback.get("id")
        msg = callback.get("message", {})
        chat_id = str(msg.get("chat", {}).get("id", ""))
        user_id = callback.get("from", {}).get("id")
        message_id = msg.get("message_id")

        if not data.startswith("dept|") and not data.startswith(BIND_PREFIX + "|") \
                and not data.startswith("tt"):
            self._answer_callback(cb_id, "Unknown action")
            return

        if data.startswith("ttdept|"):
            slug = data.replace("ttdept|", "", 1)
            dept_url = DEPARTMENT_SLUGS.get(slug)
            if not dept_url:
                self._answer_callback(cb_id, "Unknown department")
                return
            kb = _timetable_entry_buttons(self.db, dept_url)
            if not kb["count"]:
                self._answer_callback(cb_id, "Nothing available right now")
                return
            label = DEPARTMENT_LABELS.get(dept_url, dept_url)
            if chat_id and message_id:
                self._edit_text(
                    chat_id, message_id,
                    f"🗓 <b>{html.escape(label)}</b> — timetables\n\n"
                    "Tap an entry to fetch the file:",
                    kb["inline_keyboard"],
                )
            self._answer_callback(cb_id)
            return

        if data.startswith("ttsend|"):
            notice_id = data.replace("ttsend|", "", 1)
            self._answer_callback(cb_id, "⏳ Fetching the file…")
            thread_id = msg.get("message_thread_id")
            self._send_timetable_file(
                notice_id, chat_id,
                int(thread_id) if str(thread_id).isdigit() else None,
            )
            return

        if data == "ttback":
            buttons = _timetable_dept_buttons(self.db)
            if not buttons:
                self._answer_callback(cb_id, "Nothing available right now")
                return
            if chat_id and message_id:
                self._edit_text(
                    chat_id, message_id,
                    "🗓 <b>Timetables</b>\n\nPick a department:",
                    buttons["inline_keyboard"],
                )
            self._answer_callback(cb_id)
            return

        if data.startswith(BIND_PREFIX + "|"):
            if not self._is_admin(user_id):
                self._answer_callback(cb_id, "Only the admin can bind topics", show_alert=True)
                return
            _, thread_id, slug = data.split("|", 2)
            url = DEPARTMENT_SLUGS.get(slug)
            if not url or not str(thread_id).isdigit():
                self._answer_callback(cb_id, "Unknown department")
                return
            current = self.db.get_topic_bindings(chat_id)
            if current.get(str(thread_id)) == url:
                self.db.remove_topic_binding(chat_id, thread_id)
                action = "🔓 Unbound"
            else:
                self.db.set_topic_binding(chat_id, thread_id, url)
                action = "🔗 Bound"
            self._answer_callback(
                cb_id,
                f"{action}: {DEPARTMENT_LABELS.get(url, url)}",
            )
            if chat_id and message_id:
                self._edit_keyboard(chat_id, message_id, for_bind=True, thread_id=thread_id)
            return

        # The tap is only honoured if it comes from the same chat the keyboard
        # was posted in (stops random users editing someone else's selection).
        if str(callback.get("from", {}).get("id")) != chat_id:
            self._answer_callback(cb_id, "Not authorized", show_alert=True)
            return

        slug = data.replace("dept|", "", 1)
        url = DEPARTMENT_SLUGS.get(slug)
        if not url:
            self._answer_callback(cb_id, "Unknown department")
            return

        enabled = self._toggle_chat_target(chat_id, url)
        label = DEPARTMENT_LABELS.get(url, url)
        action = "✅ Enabled" if enabled else "❌ Disabled"

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
                    update_id = update["update_id"]
                    try:
                        if "message" in update:
                            self._handle(update["message"])
                        elif "callback_query" in update:
                            self._handle_callback(update["callback_query"])
                    except Exception as e:
                        logger.error("Failed to handle update %s: %s", update_id, e)
                    finally:
                        # Confirm after attempt so a crash still advances offset
                        # (Telegram will not redeliver once offset moves).
                        self._offset = update_id + 1
        except Exception as e:
            logger.error("getUpdates poll: %s", e)

    def run_forever(self):
        self._delete_webhook()
        logger.info("Command handler started")
        while True:
            try:
                self.poll_once()
            except Exception as e:
                logger.error("Command handler error: %s", e)
                time.sleep(2)
