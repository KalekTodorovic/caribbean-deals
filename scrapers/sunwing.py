from scrapers.base import BaseScraper
import re

DEST_MAP = {
    "CU": "cuba",
    "DO": "dominican-republic",
    "MX": "mexico",
    "JM": "jamaica",
    "HT": "haiti",
    "BB": "barbados",
    "AG": "antigua",
    "LC": "saint-lucia",
    "VC": "st-vincent",
    "GD": "grenada",
    "TT": "trinidad",
    "CR": "costa-rica",
    "PA": "panama",
    "CO": "colombia",
    "PR": "puerto-rico",
}

LENGTH_MAP = {
    7: "7",
    10: "10",
    14: "14",
}


class SunwingScraper(BaseScraper):
    name = "sunwing"
    base_url = "https://www.sunwing.ca"

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
        self.log.info("Searching Sunwing for %s", destination or "all destinations")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.log.error("playwright not installed")
            return []

        deals = []
        dest_slug = DEST_MAP.get(destination, "") if destination else ""
        airport_map = {"YUL": "YMQ", "YMX": "YMQ"}
        airport_code = airport_map.get(departure_airport, "YMQ")

        lengths_to_try = [7, 10, 14]

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            for nights in lengths_to_try:
                try:
                    dest_part = f"/{dest_slug}" if dest_slug else ""
                    url = (
                        f"{self.base_url}/en/vacations{dest_part}"
                        f"?departure={airport_code}"
                        f"&duration={nights}"
                    )
                    self.log.info("Sunwing URL: %s", url)
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(8000)

                    cards = await page.query_selector_all(
                        '[data-testid="vacation-card"], '
                        '[class*="VacationCard"], '
                        '[class*="vacation-card"], '
                        '[class*="product-card"], '
                        '[class*="ProductCard"], '
                        '.search-result-card'
                    )
                    self.log.info("Sunwing: found %d cards for %d nights", len(cards), nights)

                    for i, card in enumerate(cards[:30]):
                        try:
                            title = ""
                            for sel in ['[data-testid="hotel-name"]', 'h3', 'h4', '[class*="hotelName"]', '[class*="HotelName"]']:
                                el = await card.query_selector(sel)
                                if el:
                                    title = (await el.inner_text()).strip()
                                    if title:
                                        break
                            if not title:
                                title = f"Sunwing Hotel {i+1}"

                            price = 0
                            for sel in ['[data-testid="price"]', '[class*="Price"]', '[class*="price"]', '[class*="cost"]', '[class*="amount"]']:
                                el = await card.query_selector(sel)
                                if el:
                                    txt = await el.inner_text()
                                    price = self._parse_price(txt)
                                    if price > 0:
                                        break

                            stars = 4
                            for sel in ['[class*="star"]', '[class*="Star"]', '[class*="rating"]', '[class*="Rating"]']:
                                el = await card.query_selector(sel)
                                if el:
                                    txt = await el.get_attribute("aria-label") or await el.inner_text()
                                    stars = self._parse_stars(txt or "4")
                                    break

                            link = ""
                            el = await card.query_selector("a[href]")
                            if el:
                                link = await el.get_attribute("href") or ""
                                if link and not link.startswith("http"):
                                    link = self.base_url + link

                            dest_label = destination or "CARIBBEAN"

                            deal = self._make_deal(
                                destination=dest_label,
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
                                source_trip_id=f"sw_{dest_slug or 'all'}_{nights}n_{i}",
                            )
                            if price > 0:
                                deals.append(deal)
                        except Exception as e:
                            self.log.debug("Sunwing card %d parse error: %s", i, e)
                            continue

                except Exception as e:
                    self.log.error("Sunwing scrape failed for %d nights: %s", nights, e)
                    continue

            await browser.close()

        self.log.info("Sunwing: %d total deals", len(deals))
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
