import logging
import random
import time
from urllib.parse import urljoin

from lxml import html as lxml_html

logger = logging.getLogger(__name__)


class Scraper:
    def __init__(self, browser, selectors, settings):
        self.browser = browser
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
        context = self.browser.new_context(
            user_agent=random.choice(self.settings["browser"]["user_agents"]),
        )
        page = context.new_page()
        try:
            page.goto(url, timeout=self.settings["browser"]["timeout_seconds"] * 1000)
            page.wait_for_load_state("networkidle")
            html_content = page.content()
            logger.info("Fetched page: %s (%d bytes)", url, len(html_content))
            return html_content
        except Exception as e:
            logger.error("Failed to fetch %s: %s", url, e)
            return None
        finally:
            page.close()
            context.close()

    def parse_notices(self, html_content, base_url):
        tree = lxml_html.fromstring(html_content)
        sel = self.selectors
        container = tree.cssselect(sel["notice_container"])
        notices = []

        for elem in container:
            try:
                title_el = elem.cssselect(sel["title"])
                link_el = elem.cssselect(sel["link"])
                date_el = elem.cssselect(sel["date"])

                if not title_el:
                    continue

                title = title_el[0].text_content().strip()
                href = link_el[0].get("href") if link_el else None
                url = urljoin(base_url, href) if href else None
                date = date_el[0].text_content().strip() if date_el else ""

                if not url:
                    continue

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
