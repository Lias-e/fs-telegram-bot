import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

CREATE_NOTICES_TABLE = """
CREATE TABLE IF NOT EXISTS notices (
    url TEXT PRIMARY KEY,
    title TEXT,
    hash TEXT NOT NULL,
    seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_SUBSCRIPTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS subscriptions (
    chat_id TEXT PRIMARY KEY,
    chat_title TEXT,
    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

CREATE_INDEX_URL = "CREATE INDEX IF NOT EXISTS idx_notices_url ON notices(url)"


class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.execute(CREATE_NOTICES_TABLE)
        self.conn.execute(CREATE_SUBSCRIPTIONS_TABLE)
        self.conn.execute(CREATE_SETTINGS_TABLE)
        self.conn.execute(CREATE_INDEX_URL)
        self.conn.commit()

    def insert_notice(self, url, title, hash_digest):
        try:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO notices (url, title, hash) VALUES (?, ?, ?)",
                (url, title, hash_digest),
            )
            self.conn.commit()
            return cur.rowcount > 0
        except sqlite3.Error as e:
            logger.error("DB insert failed: %s", e)
            return False

    def is_duplicate(self, url):
        cur = self.conn.execute("SELECT 1 FROM notices WHERE url = ? LIMIT 1", (url,))
        return cur.fetchone() is not None

    def get_recent(self, limit=5):
        cur = self.conn.execute(
            "SELECT url, title, seen_at FROM notices ORDER BY seen_at DESC, rowid DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()

    def count(self):
        cur = self.conn.execute("SELECT COUNT(*) FROM notices")
        return cur.fetchone()[0]

    def health_check(self):
        try:
            self.conn.execute("SELECT 1")
            return True
        except sqlite3.Error:
            return False

    def add_subscription(self, chat_id, chat_title=""):
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO subscriptions (chat_id, chat_title) VALUES (?, ?)",
            (chat_id, chat_title),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def remove_subscription(self, chat_id):
        cur = self.conn.execute("DELETE FROM subscriptions WHERE chat_id = ?", (chat_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def get_subscriptions(self):
        cur = self.conn.execute("SELECT chat_id, chat_title FROM subscriptions")
        return [dict(r) for r in cur.fetchall()]

    def get_setting(self, key, default=None):
        cur = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else default

    def set_setting(self, key, value):
        self.conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
        self.conn.commit()

    def get_enabled_targets(self, all_targets):
        disabled = self.get_setting("disabled_targets", "")
        if not disabled:
            return all_targets
        disabled_list = set(disabled.split(","))
        return [t for t in all_targets if t not in disabled_list]

    def backup(self, backup_dir, retention_days=7):
        backup_path = Path(backup_dir)
        backup_path.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = backup_path / f"notices_backup_{stamp}.db"
        self.conn.commit()
        try:
            with sqlite3.connect(str(dest)) as bkp:
                self.conn.backup(bkp)
            logger.info("DB backup created: %s", dest)
            self._prune_backups(backup_path, retention_days)
        except sqlite3.Error as e:
            logger.error("DB backup failed: %s", e)

    def _prune_backups(self, backup_path, retention_days):
        cutoff = datetime.now() - timedelta(days=retention_days)
        for f in sorted(backup_path.glob("notices_backup_*.db")):
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                logger.info("Pruned old backup: %s", f)

    def close(self):
        self.conn.close()
