"""One-off: prove static HTML GET is enough; save fixtures."""
from pathlib import Path
from urllib.parse import urljoin

import httpx
from lxml import html as lxml_html

TARGETS = [
    "https://fsciences.univ-setif.dz",
    "https://fsciences.univ-setif.dz/sites_departements/informatique",
    "https://fsciences.univ-setif.dz/sites_departements/maths",
    "https://fsciences.univ-setif.dz/sites_departements/physique",
    "https://fsciences.univ-setif.dz/sites_departements/chimie",
    "https://fsciences.univ-setif.dz/sites_departements/mi",
    "https://fsciences.univ-setif.dz/sites_departements/sm",
]

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


def fixture_name(url: str) -> str:
    if url.rstrip("/").endswith("univ-setif.dz"):
        return "homepage.html"
    return f"{url.rstrip('/').split('/')[-1]}.html"


def main():
    FIXTURES.mkdir(parents=True, exist_ok=True)
    results = []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for url in TARGETS:
            r = client.get(url)
            r.raise_for_status()
            content = r.text
            name = fixture_name(url)
            (FIXTURES / name).write_text(content, encoding="utf-8")
            tree = lxml_html.fromstring(content)
            unique = set()
            for a in tree.cssselect("a[href*='/annonces/']"):
                href = a.get("href")
                if href:
                    unique.add(urljoin(url, href))
            carousel = len(tree.cssselect("div.item"))
            results.append((name, carousel, len(unique), len(content)))
            print(f"{name}: carousel={carousel} unique_annonces={len(unique)} bytes={len(content)}")

    home_unique = results[0][2]
    depts_ok = all(r[2] >= 1 for r in results[1:])
    ok = home_unique >= 20 and depts_ok
    print("PASS" if ok else "FAIL", f"homepage_unique={home_unique} depts_ok={depts_ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
