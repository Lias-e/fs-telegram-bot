from pathlib import Path

from src.config import load_selectors, load_settings
from src.scraper import Scraper

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://fsciences.univ-setif.dz"


def _scraper():
    return Scraper(load_selectors(), load_settings())


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
