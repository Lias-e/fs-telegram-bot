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

    handler = CommandHandler("token", FakeDB(), list(DEPARTMENT_LABELS.keys()), admin_id="1")
    kb = handler._build_dept_keyboard()
    for row in kb["inline_keyboard"]:
        cb = row[0]["callback_data"]
        assert cb.startswith("dept|")
        assert len(cb.encode("utf-8")) <= 64
        assert "http" not in cb
