from scrapers.base import BaseScraper
import re
from datetime import datetime, timedelta

DEST_MAP = {
    "CU": "cuba", "DO": "dominican-republic", "MX": "mexico",
    "JM": "jamaica", "BB": "barbados", "CR": "costa-rica",
}


class WestJetScraper(BaseScraper):
    name = "westjet"
    base_url = "https://www.westjet.com"

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
        self.log.info("Searching WestJet Vacations for %s", destination or "all destinations")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.log.error("playwright not installed")
            return []

        deals = []
        dests_to_try = [destination] if destination else ["DO", "MX", "JM", "CU"]

        today = datetime.now()
        checkin = (today + timedelta(days=14)).strftime("%Y-%m-%d")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            for dest_code in dests_to_try:
                dest_slug = DEST_MAP.get(dest_code, "")
                if not dest_slug:
                    continue
                for nights in [7, 10, 14]:
                    try:
                        url = (
                            f"{self.base_url}/vacations/packages"
                            f"?destination={dest_slug}"
                            f"&departure=YUL"
                            f"&departureDate={checkin}"
                            f"&duration={nights}"
                        )
                        self.log.info("WestJet URL: %s", url)
                        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                        await page.wait_for_timeout(7000)

                        cards = await page.query_selector_all(
                            '[class*="vacation-card"], '
                            '[class*="VacationCard"], '
                            '[class*="offer-card"], '
                            '[class*="product-card"], '
                            '[class*="deal-card"], '
                            '.search-result-item'
                        )
                        self.log.info("WestJet %s %dn: found %d cards", dest_code, nights, len(cards))

                        for i, card in enumerate(cards[:20]):
                            try:
                                title = ""
                                for sel in ['h3', 'h4', '[class*="hotel"]', '[class*="Hotel"]', '[class*="name"]', '[class*="title"]']:
                                    el = await card.query_selector(sel)
                                    if el:
                                        title = (await el.inner_text()).strip()
                                        if title:
                                            break
                                if not title:
                                    title = f"WestJet Hotel {i+1}"

                                price = 0
                                for sel in ['[class*="price"]', '[class*="Price"]', '[class*="amount"]', '[class*="cost"]']:
                                    el = await card.query_selector(sel)
                                    if el:
                                        txt = await el.inner_text()
                                        price = self._parse_price(txt)
                                        if price > 0:
                                            break

                                stars = 4
                                for sel in ['[class*="star"]', '[class*="rating"]']:
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
                                    deal_type="package",
                                    hotel_name=title,
                                    hotel_stars=stars,
                                    nights=nights,
                                    price_per_person=price,
                                    price_total=price * 2,
                                    all_inclusive=1 if all_inclusive else 0,
                                    direct_flight=1 if direct_only else 0,
                                    departure_airport=departure_airport,
                                    url=link,
                                    source_trip_id=f"wj_{dest_code}_{nights}n_{i}",
                                )
                                if price > 0:
                                    deals.append(deal)
                            except Exception as e:
                                self.log.debug("WestJet card %d error: %s", i, e)
                                continue

                    except Exception as e:
                        self.log.error("WestJet failed %s %dn: %s", dest_code, nights, e)
                        continue

            await browser.close()

        self.log.info("WestJet: %d total deals", len(deals))
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
