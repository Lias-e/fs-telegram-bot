import logging
import time

from src.broadcaster import Broadcaster

logger = logging.getLogger(__name__)


class Heartbeat:
    def __init__(self, broadcaster: Broadcaster, db):
        self.broadcaster = broadcaster
        self.db = db
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
                "🤖 *Bot Heartbeat*",
                f"⏱ Uptime: {self._uptime()}",
                f"📊 Total notices: {count}",
            ]
            if recent:
                lines.append("\n*Latest notices:*")
                for row in recent:
                    lines.append(f"- [{row['title'] or 'Untitled'}]({row['url']})")
            self.broadcaster.send("\n".join(lines))
            logger.info("Heartbeat sent")
        except Exception as e:
            logger.error("Heartbeat failed: %s", e)
