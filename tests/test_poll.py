import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from src.database import Database
from src.main import poll_job
from src.utils import sha256_hash


def _settings(tmp):
    return {
        "poll": {
            "targets": ["https://example.com"],
            "fast_trigger_count": 1,
            "fast_interval_minutes": 5,
            "default_interval_minutes": 30,
        },
        "browser": {
            "timeout_seconds": 5,
            "random_delay_min": 0,
            "random_delay_max": 0,
            "user_agents": ["test-agent"],
        },
        "database": {"path": str(Path(tmp) / "notices.db")},
        "telegram": {"message_max_length": 4000},
        "retry": {
            "max_attempts": 1,
            "backoff_multiplier": 1,
            "backoff_min_seconds": 1,
            "backoff_max_seconds": 1,
        },
    }


def _notices():
    return [
        {"title": "Notice A", "url": "https://example.com/annonces/1", "date": ""},
        {"title": "Notice B", "url": "https://example.com/annonces/2", "date": ""},
    ]


def test_seed_empty_db_sends_nothing(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(str(Path(tmp) / "test.db"))
        settings = _settings(tmp)
        selectors = {"link": "a[href*='/annonces/']"}

        scraper = MagicMock()
        scraper.scrape_all.return_value = _notices()
        monkeypatch.setattr("src.main.Scraper", lambda *a, **k: scraper)

        broadcaster = MagicMock()
        monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@channel")

        interval = poll_job(db, broadcaster, settings, selectors)

        assert db.count() == 2
        broadcaster.send.assert_not_called()
        assert interval == 30
        assert (Path(tmp) / "last_poll").is_file()
        db.close()


def test_send_failure_does_not_record(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(str(Path(tmp) / "test.db"))
        # Pre-seed so we are not in empty-DB mode
        db.insert_notice("https://example.com/annonces/old", "Old", sha256_hash("old"))

        settings = _settings(tmp)
        selectors = {}
        new = [{"title": "New *one*", "url": "https://example.com/annonces/new", "date": ""}]

        scraper = MagicMock()
        scraper.scrape_all.return_value = new
        scraper.fetch_notice_details.return_value = None
        monkeypatch.setattr("src.main.Scraper", lambda *a, **k: scraper)

        broadcaster = MagicMock()
        broadcaster.send.return_value = False
        monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@channel")

        poll_job(db, broadcaster, settings, selectors)

        assert not db.is_duplicate("https://example.com/annonces/new")
        broadcaster.send.assert_called_once()
        db.close()


def test_successful_send_records(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(str(Path(tmp) / "test.db"))
        db.insert_notice("https://example.com/annonces/old", "Old", sha256_hash("old"))

        settings = _settings(tmp)
        new = [{"title": "New", "url": "https://example.com/annonces/new", "date": ""}]

        scraper = MagicMock()
        scraper.scrape_all.return_value = new
        scraper.fetch_notice_details.return_value = None
        monkeypatch.setattr("src.main.Scraper", lambda *a, **k: scraper)
        monkeypatch.setattr("src.main.time.sleep", lambda *_: None)

        broadcaster = MagicMock()
        broadcaster.send.return_value = True
        monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@channel")

        poll_job(db, broadcaster, settings, selectors={})

        assert db.is_duplicate("https://example.com/annonces/new")
        db.close()


def test_topic_filter_routes_only_matching_titles(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(str(Path(tmp) / "test.db"))
        db.insert_notice("https://example.com/annonces/old", "Old", sha256_hash("old"))
        db.add_subscription("77", "M1 CS group")
        db.set_setting("is_forum:77", "1")
        db.set_topic_binding("77", "42", "https://example.com")
        db.set_topic_filter("77", "42", r"master\s*1\b|\bm\s*1\b")

        settings = _settings(tmp)
        notices = [
            {
                "title": "EMPLOI DU TEMPS MASTER 1",
                "url": "https://example.com/annonces/m1",
                "date": "",
                "source": "https://example.com",
            },
            {
                "title": "EMPLOI DU TEMPS LICENCE FINAL",
                "url": "https://example.com/annonces/lic",
                "date": "",
                "source": "https://example.com",
            },
        ]

        scraper = MagicMock()
        scraper.scrape_all.return_value = notices
        scraper.fetch_notice_details.return_value = None
        monkeypatch.setattr("src.main.Scraper", lambda *a, **k: scraper)
        monkeypatch.setattr("src.main.time.sleep", lambda *_: None)

        broadcaster = MagicMock()
        broadcaster.send.return_value = True
        monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@channel")

        poll_job(db, broadcaster, settings, selectors={})

        assert db.is_duplicate("https://example.com/annonces/m1")
        assert db.is_duplicate("https://example.com/annonces/lic")
        calls = broadcaster.send.call_args_list
        assert len(calls) == 2
        m1_targets = calls[0].kwargs["chat_ids"]
        licence_targets = calls[1].kwargs["chat_ids"]
        assert ("77", 42) in m1_targets
        assert ("77", 42) not in licence_targets
        db.close()


def test_chat_filter_routes_only_matching_titles(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(str(Path(tmp) / "test.db"))
        db.insert_notice("https://example.com/annonces/old", "Old", sha256_hash("old"))
        db.add_subscription("99", "M1 CS group")
        db.set_chat_filter("99", r"master\s*1\b|\bm\s*1\b")

        settings = _settings(tmp)
        notices = [
            {
                "title": "EMPLOI_DU_TEMPS_MASTER_1",
                "url": "https://example.com/annonces/m1",
                "date": "",
                "source": "https://example.com",
            },
            {
                "title": "CONVOCATION",
                "url": "https://example.com/annonces/conv",
                "date": "",
                "source": "https://example.com",
            },
        ]

        scraper = MagicMock()
        scraper.scrape_all.return_value = notices
        scraper.fetch_notice_details.return_value = None
        monkeypatch.setattr("src.main.Scraper", lambda *a, **k: scraper)
        monkeypatch.setattr("src.main.time.sleep", lambda *_: None)

        broadcaster = MagicMock()
        broadcaster.send.return_value = True
        monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@channel")

        poll_job(db, broadcaster, settings, selectors={})

        calls = broadcaster.send.call_args_list
        assert len(calls) == 2
        assert ("99", None) in calls[0].kwargs["chat_ids"]
        assert ("99", None) not in calls[1].kwargs["chat_ids"]
        db.close()
