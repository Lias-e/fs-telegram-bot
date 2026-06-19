import logging
import sqlite3
import shutil
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

CREATE_NOTICES_TABLE = """
CREATE TABLE IF NOT EXISTS notices (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT,
    hash TEXT NOT NULL,
    seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_INDEX_HASH = """
CREATE INDEX IF NOT EXISTS idx_notices_hash ON notices(hash)
"""


class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.execute(CREATE_NOTICES_TABLE)
        self.conn.execute(CREATE_INDEX_HASH)
        self.conn.commit()

    def insert_notice(self, notice_id, url, title, hash_digest):
        try:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO notices (id, url, title, hash) VALUES (?, ?, ?, ?)",
                (notice_id, url, title, hash_digest),
            )
            self.conn.commit()
            return cur.rowcount > 0
        except sqlite3.Error as e:
            logger.error("DB insert failed: %s", e)
            return False

    def is_duplicate(self, hash_digest):
        cur = self.conn.execute("SELECT 1 FROM notices WHERE hash = ? LIMIT 1", (hash_digest,))
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
