import html
import logging
import time

logger = logging.getLogger(__name__)


class Heartbeat:
    def __init__(self, broadcaster, db, admin_id):
        self.broadcaster = broadcaster
        self.db = db
        self.admin_id = admin_id
        self.start_time = time.time()

    def _uptime(self):
        elapsed = int(time.time() - self.start_time)
        days, remainder = divmod(elapsed, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        return " ".join(parts)

    def send(self):
        try:
            count = self.db.count()
            recent = self.db.get_recent(3)
            lines = [
                "🤖 <b>Bot Heartbeat</b>",
                f"⏱ Uptime: {html.escape(self._uptime())}",
                f"📊 Total notices: {count}",
            ]
            if recent:
                lines.append("\n<b>Latest notices:</b>")
                for row in recent:
                    title = html.escape(row["title"] or "Untitled")
                    url = html.escape(row["url"], quote=True)
                    lines.append(f'- <a href="{url}">{title}</a>')
            self.broadcaster.send_to_admin("\n".join(lines), self.admin_id)
            logger.info("Heartbeat sent to admin")
        except Exception as e:
            logger.error("Heartbeat failed: %s", e)
