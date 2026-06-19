from src.utils import format_notice, sha256_hash, split_text


def test_sha256_hash():
    h = sha256_hash("hello")
    assert len(h) == 64
    assert sha256_hash("hello") == sha256_hash("hello")
    assert sha256_hash("hello") != sha256_hash("world")


def test_split_text_under_limit():
    assert split_text("short text", 100) == ["short text"]


def test_split_text_over_limit():
    long = "hello world " * 100
    parts = split_text(long, 50)
    assert len(parts) > 1
    assert all(len(p) <= 50 for p in parts)


def test_format_notice():
    result = format_notice("Test Title", "http://example.com", "2026-06-19")
    assert "Test Title" in result
    assert "http://example.com" in result
    assert "2026-06-19" in result


def test_format_notice_no_date():
    result = format_notice("No Date", "http://example.com")
    assert "No Date" in result
    assert "📅" not in result
