import tempfile
from pathlib import Path

from src.database import Database


def _make_db(tmp):
    return Database(str(Path(tmp) / "test.db"))


def test_init_db():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp)
        assert db.health_check() is True
        db.close()


def test_insert_and_deduplicate():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp)
        assert db.insert_notice("id1", "http://example.com/1", "Notice 1", "abc123")
        assert db.count() == 1
        assert not db.insert_notice("id1", "http://example.com/1", "Notice 1", "abc123")
        assert db.count() == 1
        db.close()


def test_is_duplicate():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp)
        assert not db.is_duplicate("nonexistent")
        db.insert_notice("id2", "http://example.com/2", "Notice 2", "def456")
        assert db.is_duplicate("def456")
        db.close()


def test_get_recent():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp)
        db.insert_notice("a", "http://a.com", "A", "aaa")
        db.insert_notice("b", "http://b.com", "B", "bbb")
        recent = db.get_recent(2)
        assert len(recent) == 2
        assert recent[0]["title"] == "B"
        db.close()


def test_subscriptions():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp)
        assert db.add_subscription("-100123", "Test Chat")
        assert not db.add_subscription("-100123", "Test Chat")
        subs = db.get_subscriptions()
        assert len(subs) == 1
        assert subs[0]["chat_id"] == "-100123"
        assert db.remove_subscription("-100123")
        assert len(db.get_subscriptions()) == 0
        db.close()


def test_settings():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp)
        assert db.get_setting("foo") is None
        db.set_setting("foo", "bar")
        assert db.get_setting("foo") == "bar"
        db.set_setting("foo", "baz")
        assert db.get_setting("foo") == "baz"
        db.close()


def test_enabled_targets():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp)
        targets = ["a", "b", "c"]
        assert db.get_enabled_targets(targets) == ["a", "b", "c"]
        db.set_setting("disabled_targets", "b")
        assert db.get_enabled_targets(targets) == ["a", "c"]
        db.close()
