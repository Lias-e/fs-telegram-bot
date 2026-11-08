import logging
import random
import re
import time
from pathlib import Path
from urllib.parse import unquote, urljoin

import httpx
from lxml import html as lxml_html

logger = logging.getLogger(__name__)

ATTACHMENT_RE = re.compile(r"\.(pdf|jpe?g|png)$", re.IGNORECASE)
READ_MORE_TEXTS = {"قراءة المزيد", "lire la suite", "read more"}
MAX_ATTACHMENT_BYTES = 40 * 1024 * 1024  # Telegram bot API document limit is 50 MB
MAX_ATTACHMENTS_PER_NOTICE = 3

DESKTOP_BROWSERS = [
    # (platform string for Sec-CH-UA-Platform, full Chrome UA)
    ("\"Windows\"",
     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    ("\"macOS\"",
     "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"),
    ("\"Windows\"",
     "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"),
    ("\"Linux\"",
     "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"),
]


class Scraper:
    def __init__(self, selectors, settings):
        self.selectors = selectors
        self.settings = settings
        # One consistent browser fingerprint per Scraper instance (a poll
        # session) — real users don't switch browser between sub-requests.
        self._platform, self._user_agent = random.choice(DESKTOP_BROWSERS)

    def _browser_headers(self):
        """
        Realistic desktop-Chromium headers: client hints match the UA
        version, languages fit the DZ audience, fetch metadata looks like
        a user navigation. Accept-Encoding is intentionally omitted —
        httpx advertises exactly the codecs it can decode.
        """
        major = (re.search(r"Chrome/(\d+)", self._user_agent) or [None, "131"])[1]
        # "Not/A)Brand" is the GREASE-style placeholder Chromium sends; the
        # value is noise by design — the UA version is what matters.
        brands = (
            f"\"Not/A)Brand\";v=\"8\", \"Chromium\";v=\"{major}\", "
            f"\"Google Chrome\";v=\"{major}\""
        )
        return {
            "User-Agent": self._user_agent,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8,"
                "application/signed-exchange;v=b3;q=0.7"
            ),
            "Accept-Language": "fr-DZ,fr;q=0.9,ar-DZ,ar;q=0.8,en;q=0.7",
            "Sec-CH-UA": brands,
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": self._platform,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

    def _random_delay(self):
        delay = random.uniform(
            self.settings["browser"]["random_delay_min"],
            self.settings["browser"]["random_delay_max"],
        )
        time.sleep(delay)

    def fetch_page(self, url):
        self._random_delay()
        timeout = self.settings["browser"]["timeout_seconds"]
        try:
            with httpx.Client(
                timeout=timeout,
                follow_redirects=True,
                headers=self._browser_headers(),
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
                html_content = resp.text
            logger.info("Fetched page: %s (%d bytes)", url, len(html_content))
            return html_content
        except Exception as e:
            logger.error("Failed to fetch %s: %s", url, e)
            return None

    def parse_notices(self, html_content, base_url, department="General"):
        tree = lxml_html.fromstring(html_content)
        link_sel = self.selectors.get("link", "a[href*='/annonces/']")
        notices = []
        seen = set()

        for elem in tree.cssselect(link_sel):
            try:
                href = elem.get("href")
                if not href:
                    continue
                url = urljoin(base_url, href)
                if url in seen:
                    continue
                seen.add(url)

                # The listing link text is a generic "Read more" button – find the
                # real title in the heading of the same carousel caption.
                title = (elem.text_content() or "").strip()
                if title.lower() in READ_MORE_TEXTS or not title:
                    captions = elem.xpath(
                        "ancestor::*[contains(@class,'carousel-caption')]"
                    )
                    heading = None
                    if captions:
                        hs = captions[0].cssselect("h2") or captions[0].cssselect("h3")
                        if hs:
                            heading = hs[0]
                    if heading is None:
                        for cand in elem.xpath("preceding::h2[1] | preceding::h3[1]"):
                            heading = cand
                            break
                    heading_text = (
                        (heading.text_content() or "").strip() if heading is not None else ""
                    )
                    if heading_text:
                        title = heading_text
                if not title:
                    title = url

                date = ""
                captions = elem.xpath(
                    "ancestor::*[contains(@class,'carousel-caption')]"
                )
                if captions:
                    ds = captions[0].cssselect("h3")
                    if ds:
                        date = ds[0].text_content().strip()
                if not date:
                    for d_el in elem.xpath("preceding::h3[1]"):
                        date = d_el.text_content().strip()
                        break

                notices.append({
                    "title": title,
                    "url": url,
                    "date": date,
                    "department": department,
                    "source": base_url,
                })
            except Exception as e:
                logger.warning("Skipped notice element: %s", e)
                continue

        logger.info("Parsed %d notices from page", len(notices))
        return notices

    def scrape(self, url):
        department = self.settings.get("departments", {}).get(url, "General")
        html = self.fetch_page(url)
        if not html:
            return []
        return self.parse_notices(html, url, department=department)

    def scrape_all(self, urls):
        all_notices = []
        for url in urls:
            notices = self.scrape(url)
            all_notices.extend(notices)
        return all_notices

    def fetch_notice_details(self, url):
        """
        Fetch a single notice page and extract its real title, subtitle,
        body text and attachment URLs (PDFs / images embedded as iframes,
        links or images under the notice panel).
        Returns None when the page cannot be fetched.
        """
        html_content = self.fetch_page(url)
        if not html_content:
            return None
        try:
            tree = lxml_html.fromstring(html_content)
        except Exception as e:
            logger.warning("Notice page parse failed for %s: %s", url, e)
            return None

        detail = {"title": "", "subtitle": "", "body": "", "attachments": []}

        labels = tree.cssselect(".breadcrumb label")
        if labels:
            detail["title"] = (labels[0].text_content() or "").strip()
        headings = tree.cssselect(".annonce .panel-heading")
        if headings:
            detail["subtitle"] = (headings[0].text_content() or "").strip()
        bodies = tree.cssselect(".annonce .panel-body .container-fluid2")
        if not bodies:
            bodies = tree.cssselect(".annonce .panel-body")
        if bodies:
            body = " ".join(bodies[0].text_content().split())
            detail["body"] = body[:1200]

        seen = set()
        candidates = []
        candidates.extend(tree.cssselect(".annonce a[href], .annonce iframe[src]"))
        candidates.extend(tree.cssselect(".annonce img[src]"))
        for el in candidates:
            href = el.get("src") or el.get("href")
            if not href:
                continue
            u = urljoin(url, href)
            path = u.split("#")[0].split("?")[0]
            if not ATTACHMENT_RE.search(path):
                continue
            if u in seen:
                continue
            seen.add(u)
            filename = unquote(path.rstrip("/").split("/")[-1]) or "file"
            kind = "photo" if ATTACHMENT_RE.search(path) and re.search(r"\.(jpe?g|png)$", path, re.I) else "document"
            detail["attachments"].append({"url": u, "filename": filename, "kind": kind})

        logger.info(
            "Notice details %s: title=%r, %d attachment(s)",
            url, detail["title"], len(detail["attachments"]),
        )
        return detail

    def download_attachment(self, attachment, dest_dir):
        """
        Download an attachment to dest_dir, retrying a few times because the
        source server often stalls mid-stream (read timeouts). A retry usually
        succeeds immediately, which keeps the description + PDF captioned in
        one message instead of two. Returns the local Path on success, None
        otherwise. Caps download size and filters by response Content-Type to
        avoid saving HTML error pages as files.
        """
        url = attachment["url"]
        kind = attachment["kind"]
        filename = re.sub(r"[^\w.\- ()]+", "_", attachment["filename"]) or "file"
        allowed_content = (
            {"application/pdf"} if kind == "document"
            else {"image/jpeg", "image/png", "image/webp"}
        )
        browser_cfg = self.settings["browser"]
        # Attachments (especially PDFs) stream slowly from the source host;
        # allow a longer read timeout than page fetches.
        timeout = browser_cfg.get("attachment_timeout_seconds", 120)
        max_attempts = browser_cfg.get("attachment_download_attempts", 3)
        for attempt in range(1, max_attempts + 1):
            target = Path(dest_dir, filename)
            try:
                Path(dest_dir).mkdir(parents=True, exist_ok=True)
                headers = self._browser_headers()
                # Same click: an embedded document request, not a fresh navigation
                headers["Sec-Fetch-Site"] = "same-origin"
                headers.pop("Sec-Fetch-User", None)
                headers.pop("Upgrade-Insecure-Requests", None)
                headers["Accept"] = (
                    "application/pdf,application/vnd.ms-excel,application/vnd.ms-powerpoint,"
                    "application/msword,*/*"
                    if kind == "document"
                    else "image/avif,image/webp,image/apng,image/jpeg,image/png,*/*;q=0.8"
                )
                with httpx.Client(
                    timeout=timeout,
                    follow_redirects=True,
                    headers=headers,
                ) as client:
                    with client.stream("GET", url) as resp:
                        resp.raise_for_status()
                        ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                        if ctype and ctype not in allowed_content:
                            logger.warning("Unexpected content-type %s for %s", ctype, url)
                            return None
                        wrote = 0
                        with open(target, "wb") as fh:
                            for chunk in resp.iter_bytes(65536):
                                wrote += len(chunk)
                                if wrote > MAX_ATTACHMENT_BYTES:
                                    logger.warning("Attachment too large: %s", url)
                                    fh.close()
                                    target.unlink(missing_ok=True)
                                    return None
                                fh.write(chunk)
                logger.info("Downloaded attachment %s (%d bytes)", target.name, wrote)
                return target
            except Exception as e:
                # A partial download may have been left behind — clean it up
                # before deciding whether to retry.
                target.unlink(missing_ok=True)
                logger.error(
                    "Attachment download failed (attempt %d/%d) for %s: %s",
                    attempt, max_attempts, url, e,
                )
                if attempt < max_attempts:
                    wait = min(5 * 2 ** (attempt - 1), 30)
                    time.sleep(wait)
        return None
