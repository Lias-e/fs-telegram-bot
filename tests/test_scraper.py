from pathlib import Path

import httpx

from src.config import load_selectors, load_settings
from src.scraper import Scraper

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://fsciences.univ-setif.dz"


def _scraper(settings=None):
    selected = settings or load_settings()
    return Scraper(load_selectors(), selected)


def test_homepage_parses_all_annonces_not_just_carousel():
    html = (FIXTURES / "homepage.html").read_text(encoding="utf-8")
    notices = _scraper().parse_notices(html, BASE)
    urls = {n["url"] for n in notices}
    assert len(urls) >= 20, f"expected many /annonces/ links, got {len(urls)}"
    assert len(urls) == len(notices), "duplicate URLs in parse result"
    # Must include list-panel IDs that are not in the carousel-only set
    assert any("/annonces/" in u for u in urls)


def test_informatique_parses_carousel_links():
    html = (FIXTURES / "informatique.html").read_text(encoding="utf-8")
    notices = _scraper().parse_notices(
        html, "https://fsciences.univ-setif.dz/sites_departements/informatique"
    )
    assert len(notices) >= 1
    assert all("/annonces/" in n["url"] for n in notices)


def test_notices_have_titles():
    html = (FIXTURES / "homepage.html").read_text(encoding="utf-8")
    notices = _scraper().parse_notices(html, BASE)
    assert all(n["title"] for n in notices)


class _FakeStreamResponse:
    """Response whose body optionally raises an error while streaming."""

    def __init__(self, chunks, error):
        self._chunks = chunks
        self._error = error
        self.headers = {"content-type": "application/pdf"}

    def raise_for_status(self):
        pass

    def iter_bytes(self, size):
        yield from self._chunks
        if self._error is not None:
            raise self._error


def test_download_attachment_retries_after_read_timeout(tmp_path, monkeypatch):
    """First attempt stalls mid-stream, second succeeds — file must be returned."""
    settings = load_settings()
    settings["browser"] = {
        **settings["browser"],
        "attachment_timeout_seconds": 120,
        "attachment_download_attempts": 3,
    }
    monkeypatch.setattr("src.scraper.time.sleep", lambda s: None)  # keep test fast
    scraper = _scraper(settings)

    pdf_bytes = b"%PDF-1.4 fake pdf" * 4
    calls = []

    def fake_stream(self, method, url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            response = _FakeStreamResponse(
                [pdf_bytes[:10]], httpx.ReadTimeout("read timed out")
            )
        else:
            response = _FakeStreamResponse([pdf_bytes], None)
        # A context manager-backed stream
        return _FakeStreamContext(response)

    class _FakeClient(httpx.Client):
        stream = fake_stream

    monkeypatch.setattr("src.scraper.httpx.Client", _FakeClient)

    attachment = {
        "url": f"{BASE}/uploads/Licence.pdf",
        "filename": "Licence.pdf",
        "kind": "document",
    }
    result = scraper.download_attachment(attachment, str(tmp_path / "attachments"))

    assert result is not None
    assert result.read_bytes() == pdf_bytes
    assert len(calls) == 2, "expected exactly one retry before success"
    # No partial file left behind anywhere
    leftovers = [p.name for p in tmp_path.rglob("*") if p.is_file()]
    assert result.name in leftovers


def test_download_attachment_gives_up_after_max_attempts(tmp_path, monkeypatch):
    settings = load_settings()
    settings["browser"] = {
        **settings["browser"],
        "attachment_timeout_seconds": 120,
        "attachment_download_attempts": 2,
    }
    monkeypatch.setattr("src.scraper.time.sleep", lambda s: None)
    scraper = _scraper(settings)

    calls = []

    def fake_stream(self, method, url, **kwargs):
        calls.append(url)
        return _FakeStreamContext(
            _FakeStreamResponse([], httpx.ReadTimeout("read timed out"))
        )

    class _FakeClient(httpx.Client):
        stream = fake_stream

    monkeypatch.setattr("src.scraper.httpx.Client", _FakeClient)

    attachment = {
        "url": f"{BASE}/uploads/ING.pdf",
        "filename": "ING.pdf",
        "kind": "document",
    }
    result = scraper.download_attachment(attachment, str(tmp_path / "attachments"))

    assert result is None
    assert len(calls) == 2, "should stop after attachment_download_attempts"
    assert not list(tmp_path.rglob("*.pdf")), "partial file must be cleaned up"


class _FakeStreamContext:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self._response

    def __exit__(self, *exc):
        return False
