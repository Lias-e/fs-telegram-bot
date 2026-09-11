import logging
import random
import time
from urllib.parse import urljoin

import httpx
from lxml import html as lxml_html

logger = logging.getLogger(__name__)


class Scraper:
    def __init__(self, selectors, settings):
        self.selectors = selectors
        self.settings = settings

    def _random_delay(self):
        delay = random.uniform(
            self.settings["browser"]["random_delay_min"],
            self.settings["browser"]["random_delay_max"],
        )
        time.sleep(delay)

    def fetch_page(self, url):
        self._random_delay()
        timeout = self.settings["browser"]["timeout_seconds"]
        user_agent = random.choice(self.settings["browser"]["user_agents"])
        try:
            with httpx.Client(
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": user_agent},
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
                html_content = resp.text
            logger.info("Fetched page: %s (%d bytes)", url, len(html_content))
            return html_content
        except Exception as e:
            logger.error("Failed to fetch %s: %s", url, e)
            return None

    def parse_notices(self, html_content, base_url):
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

                title = (elem.text_content() or "").strip()
                if not title:
                    # Prefer nearest preceding heading text
                    for heading in elem.xpath(
                        "preceding::h1[1] | preceding::h2[1] | preceding::h3[1]"
                    ):
                        title = (heading.text_content() or "").strip()
                        if title:
                            break
                if not title:
                    title = url

                date = ""
                date_el = elem.cssselect(self.selectors.get("date", ".carousel-caption h3"))
                if date_el:
                    date = date_el[0].text_content().strip()
                else:
                    # Caption sibling / parent carousel date if present
                    parent_dates = elem.xpath(
                        "ancestor::div[contains(@class,'item')]//*[contains(@class,'carousel-caption')]//h3"
                    )
                    if parent_dates:
                        date = (parent_dates[0].text_content() or "").strip()

                notices.append({
                    "title": title,
                    "url": url,
                    "date": date,
                })
            except Exception as e:
                logger.warning("Skipped notice element: %s", e)
                continue

        logger.info("Parsed %d notices from page", len(notices))
        return notices

    def scrape(self, url):
        html = self.fetch_page(url)
        if not html:
            return []
        return self.parse_notices(html, url)

    def scrape_all(self, urls):
        all_notices = []
        for url in urls:
            notices = self.scrape(url)
            all_notices.extend(notices)
        return all_notices
