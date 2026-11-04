from src.commands import DEPARTMENT_LABELS, DEPARTMENT_SLUGS, URL_TO_SLUG, CommandHandler


def test_all_callback_data_within_64_bytes():
    for slug, url in DEPARTMENT_SLUGS.items():
        data = f"dept|{slug}"
        assert len(data.encode("utf-8")) <= 64, data
        assert URL_TO_SLUG[url] == slug
        assert url in DEPARTMENT_LABELS


def test_build_dept_keyboard_uses_slugs():
    class FakeDB:
        def get_setting(self, key, default=None):
            return default or ""

        def get_chat_targets(self, chat_id):
            return None  # follow the global default

        def default_enabled_targets(self, all_targets):
            return list(all_targets)

    handler = CommandHandler("token", FakeDB(), list(DEPARTMENT_LABELS.keys()), admin_id="1")
    kb = handler._build_dept_keyboard("123")
    for row in kb["inline_keyboard"]:
        cb = row[0]["callback_data"]
        assert cb.startswith("dept|")
        assert len(cb.encode("utf-8")) <= 64
        assert "http" not in cb


def test_level_regexes():
    import re

    from src.commands import LEVEL_REGEX

    assert re.search(LEVEL_REGEX["master1"], "EMPLOI DU TEMPS MASTER 1", re.I)
    assert not re.search(LEVEL_REGEX["master1"], "EMPLOI DU TEMPS MASTER 2", re.I)
    assert re.search(LEVEL_REGEX["master2"], "EMPLOIS DU TEMPS M1-M2 CHIMIE", re.I)
    assert not re.search(LEVEL_REGEX["master2"], "EMPLOI DU TEMPS MASTER 1", re.I)
    assert re.search(LEVEL_REGEX["licence"], "EMPLOI DU TEMPS LICENCE", re.I)
    assert not re.search(LEVEL_REGEX["licence"], "EMPLOI DU TEMPS MASTER 1", re.I)


def test_bind_flow_with_level_options(monkeypatch):
    import tempfile
    from pathlib import Path

    from src.commands import LEVEL_REGEX, CommandHandler
    from src.database import Database

    edits = []
    replies = []

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(str(Path(tmp) / "test.db"))
        handler = CommandHandler("token", db, list(DEPARTMENT_LABELS.keys()), admin_id=111)
        monkeypatch.setattr(handler, "_answer_callback", lambda *a, **k: replies.append(a))
        monkeypatch.setattr(handler, "_edit_keyboard", lambda *a, **k: None)
        monkeypatch.setattr(
            handler, "_edit_text", lambda *a, **k: edits.append(a)
        )

        def callback(data):
            return {
                "id": "cb1",
                "data": data,
                "message": {"chat": {"id": 123}, "message_id": 5},
                "from": {"id": 111},
            }

        # 1. Bind topic 42 to Computer Science -> level picker appears
        handler._handle_callback(callback("bind|42|informatique"))
        bindings = db.get_topic_bindings("123")
        assert bindings == {
            "42": "https://fsciences.univ-setif.dz/sites_departements/informatique"
        }
        assert any("level" in str(e) for e in edits)

        # 2. Pick "Master 1" -> stored as the topic's title filter
        handler._handle_callback(callback("lvl|42|master1"))
        assert db.get_topic_filter("123", "42") == LEVEL_REGEX["master1"]

        # 3. Switch level works
        handler._handle_callback(callback("lvl|42|master2"))
        assert db.get_topic_filter("123", "42") == LEVEL_REGEX["master2"]

        # 4. "All levels" clears the filter
        handler._handle_callback(callback("lvl|42|all"))
        assert db.get_topic_filter("123", "42") is None

        # 5. Non-admin cannot set levels
        handler._handle_callback({
            "id": "cb2",
            "data": "lvl|42|master1",
            "message": {"chat": {"id": 123}, "message_id": 5},
            "from": {"id": 999},
        })
        assert db.get_topic_filter("123", "42") is None

        # 6. Unbinding clears the level filter too
        handler._handle_callback(callback("lvl|42|master1"))
        handler._handle_callback(callback("bind|42|informatique"))
        assert db.get_topic_bindings("123") == {}
        assert db.get_topic_filter("123", "42") is None
        db.close()
