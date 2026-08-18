from scrapers.base import BaseScraper
import re
from datetime import datetime, timedelta


class ExpediaScraper(BaseScraper):
    name = "expedia"
    base_url = "https://www.expedia.ca"

    async def search(
        self,
        destination: str = None,
        departure_airport: str = "YUL",
        date_from: str = None,
        date_to: str = None,
        nights_min: int = None,
        nights_max: int = None,
        max_price: float = None,
        all_inclusive: bool = True,
        direct_only: bool = False,
        min_stars: int = None,
    ) -> list[dict]:
        self.log.info("Searching Expedia.ca for %s", destination or "all destinations")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.log.error("playwright not installed")
            return []

        deals = []
        dest_searches = {
            "CU": "Havana Cuba", "DO": "Punta Cana Dominican Republic",
            "MX": "Cancun Mexico", "JM": "Montego Bay Jamaica",
            "BB": "Barbados", "CR": "San Jose Costa Rica",
        }

        if destination:
            search_list = [(destination, dest_searches.get(destination, "Caribbean"))]
        else:
            search_list = [
                ("DO", "Punta Cana Dominican Republic"),
                ("MX", "Cancun Mexico"),
                ("JM", "Montego Bay Jamaica"),
            ]

        today = datetime.now()
        checkin = (today + timedelta(days=14)).strftime("%Y-%m-%d")
        checkout = (today + timedelta(days=21)).strftime("%Y-%m-%d")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            for dest_code, search_term in search_list:
                try:
                    url = (
                        f"{self.base_url}/Hotel-Search"
                        f"?destination={search_term.replace(' ', '%20')}"
                        f"&startDate={checkin}"
                        f"&endDate={checkout}"
                        f"&adults=2"
                        f"&currency=CAD"
                    )
                    self.log.info("Expedia URL: %s", url)
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(6000)

                    cards = await page.query_selector_all(
                        '[class*="uitk-card"], '
                        '[data-stid="property-listing"], '
                        '[class*="PropertyCard"], '
                        '[class*="package-card"]'
                    )
                    self.log.info("Expedia %s: found %d cards", dest_code, len(cards))

                    for i, card in enumerate(cards[:25]):
                        try:
                            title = ""
                            for sel in ['h3', 'h4', '[class*="name"]', '[class*="Name"]', '[data-stid="content-hotel-title"]']:
                                el = await card.query_selector(sel)
                                if el:
                                    title = (await el.inner_text()).strip()
                                    if title:
                                        break
                            if not title:
                                title = f"Expedia Hotel {i+1}"

                            price = 0
                            for sel in ['[class*="price"]', '[class*="Price"]', '[data-stid="content-hotel-price"]', '.uitk-text']:
                                el = await card.query_selector(sel)
                                if el:
                                    txt = await el.inner_text()
                                    price = self._parse_price(txt)
                                    if price > 0:
                                        break

                            stars = 4
                            for sel in ['[class*="star"]', '[class*="Star"]', '[class*="rating"]']:
                                el = await card.query_selector(sel)
                                if el:
                                    txt = await el.inner_text() or await el.get_attribute("aria-label") or "4"
                                    stars = self._parse_stars(txt)
                                    break

                            link = ""
                            el = await card.query_selector("a[href]")
                            if el:
                                link = await el.get_attribute("href") or ""
                                if link and not link.startswith("http"):
                                    link = self.base_url + link

                            deal = self._make_deal(
                                destination=dest_code,
                                deal_type="hotel",
                                hotel_name=title,
                                hotel_stars=stars,
                                nights=7,
                                price_per_person=price,
                                price_total=price * 2,
                                all_inclusive=1 if all_inclusive else 0,
                                direct_flight=0,
                                departure_airport=departure_airport,
                                url=link,
                                source_trip_id=f"ex_{dest_code}_{checkin}_{i}",
                            )
                            if price > 0:
                                deals.append(deal)
                        except Exception as e:
                            self.log.debug("Expedia card %d error: %s", i, e)
                            continue

                except Exception as e:
                    self.log.error("Expedia scrape failed for %s: %s", dest_code, e)
                    continue

            await browser.close()

        self.log.info("Expedia: %d total deals", len(deals))
        return deals

    def _parse_price(self, text: str) -> float:
        nums = re.findall(r'[\d,]+\.?\d*', text.replace(',', ''))
        if nums:
            val = float(nums[0])
            if val < 10:
                val *= 1000
            return val
        return 0.0

    def _parse_stars(self, text: str) -> int:
        nums = re.findall(r'\d', text)
        if nums:
            s = int(nums[0])
            if 1 <= s <= 5:
                return s
        return 4
