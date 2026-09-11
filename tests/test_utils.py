from src.utils import extract_date, format_notice, sha256_hash, split_text


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


def test_format_notice_html():
    result = format_notice("Test Title", "http://example.com", "2026-06-19")
    assert "<b>Test Title</b>" in result
    assert 'href="http://example.com"' in result
    assert "2026-06-19" in result
    assert "📄" in result


def test_format_notice_escapes_special_chars():
    result = format_notice("A *bold* _and_ <tag> & more", "http://example.com/a?x=1&y=2")
    assert "<b>A *bold* _and_ &lt;tag&gt; &amp; more</b>" in result
    assert "<tag>" not in result
    assert 'href="http://example.com/a?x=1&amp;y=2"' in result
    assert "parse_mode" not in result
    # Must not use legacy Markdown wrappers
    assert result.count("*") == 2  # only the literal asterisks from the title

def test_format_notice_no_date():
    result = format_notice("No Date", "http://example.com")
    assert "No Date" in result
    assert "📅" not in result


def test_extract_date_arabic_with_space():
    assert extract_date("10 سبتمبر 2026") == "2026-09-10"


def test_extract_date_arabic_no_space():
    assert extract_date("المنشور رقم 1 ( 02جوان 2025)") == "2025-06-02"
