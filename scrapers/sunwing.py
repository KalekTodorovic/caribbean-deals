from scrapers.base import BaseScraper

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

        url = f"{self.base_url}/en/vacations/search"
        params = f"?departure={airport_code}"
        if dest_slug:
            params += f"&destination={dest_slug}"

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            try:
                await page.goto(url + params, timeout=30000, wait_until="networkidle")
                await page.wait_for_timeout(5000)

                cards = await page.query_selector_all('[data-testid="vacation-card"], .vacation-card, .search-result-card')
                if not cards:
                    cards = await page.query_selector_all('.card, .result-item, [class*="product"]')

                self.log.info("Found %d cards on Sunwing", len(cards))

                for i, card in enumerate(cards[:50]):
                    try:
                        title_el = await card.query_selector('.card-title, .hotel-name, h3, h4, [class*="name"]')
                        title = await title_el.inner_text() if title_el else f"Sunwing Hotel {i+1}"

                        price_el = await card.query_selector('.price, [class*="price"], [class*="cost"]')
                        price_text = await price_el.inner_text() if price_el else "0"
                        price = self._parse_price(price_text)

                        stars_el = await card.query_selector('[class*="star"], .rating')
                        stars_text = await stars_el.inner_text() if stars_el else "4"
                        stars = self._parse_stars(stars_text)

                        link_el = await card.query_selector('a')
                        link = await link_el.get_attribute('href') if link_el else ""
                        if link and not link.startswith("http"):
                            link = self.base_url + link

                        deal = self._make_deal(
                            destination=destination or "CARIBBEAN",
                            hotel_name=title.strip(),
                            hotel_stars=stars,
                            price_per_person=price,
                            price_total=price * 2,
                            all_inclusive=1 if all_inclusive else 0,
                            direct_flight=1 if direct_only else 0,
                            departure_airport=departure_airport,
                            url=link,
                            source_trip_id=f"sw_{i}_{destination or 'all'}",
                        )
                        if price > 0:
                            deals.append(deal)
                    except Exception as e:
                        self.log.debug("Failed to parse card %d: %s", i, e)
                        continue

            except Exception as e:
                self.log.error("Sunwing scrape failed: %s", e)
            finally:
                await browser.close()

        self.log.info("Sunwing: %d deals found", len(deals))
        return deals

    def _parse_price(self, text: str) -> float:
        import re
        nums = re.findall(r'[\d,]+\.?\d*', text.replace(',', ''))
        if nums:
            val = float(nums[0])
            if val < 10:
                val *= 1000
            return val
        return 0.0

    def _parse_stars(self, text: str) -> int:
        import re
        nums = re.findall(r'\d', text)
        if nums:
            s = int(nums[0])
            if 1 <= s <= 5:
                return s
        return 4
