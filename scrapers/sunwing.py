from scrapers.base import BaseScraper
import re


class SunwingScraper(BaseScraper):
    name = "sunwing"
    base_url = "https://www.sunwing.ca"
    DEPARTURE_CODE = "YUL"

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
        self.log.info("Searching Sunwing for %s (from %s)", destination or "all destinations", departure_airport)
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.log.error("playwright not installed")
            return []

        deals = []

        pages_to_scrape = [
            "/en/promotion/packages/all-inclusive-vacation-packages",
            "/en/promotion/packages/last-minute-vacations",
            "/en/best-vacations",
        ]

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            for page_path in pages_to_scrape:
                try:
                    url = self.base_url + page_path
                    self.log.info("Sunwing URL: %s", url)
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(8000)
                    for _ in range(3):
                        await page.evaluate("window.scrollBy(0, 800)")
                        await page.wait_for_timeout(2000)

                    cards = await page.query_selector_all(
                        '[class*="CardType-module--card"]'
                    )
                    self.log.info("Sunwing %s: found %d cards", page_path, len(cards))

                    for i, card in enumerate(cards[:30]):
                        try:
                            text = await card.inner_text()
                            lines = [l.strip() for l in text.split("\n") if l.strip()]
                            if len(lines) < 4:
                                continue

                            hotel_name = lines[1] if len(lines) > 1 else f"Sunwing Hotel {i+1}"

                            price = 0
                            nights = 7
                            for line in lines:
                                m = re.match(r'^\$(\d[\d,]*)$', line)
                                if m:
                                    val = float(m.group(1).replace(',', ''))
                                    if val > price:
                                        price = val
                                m2 = re.match(r'^(\d+)\s*day', line)
                                if m2:
                                    nights = int(m2.group(1))

                            if price <= 0:
                                continue

                            dest_line = lines[0] if lines else ""
                            dest_code = self._guess_dest(dest_line, destination)

                            link = ""
                            el = await card.query_selector("a[href]")
                            if el:
                                link = await el.get_attribute("href") or ""
                                if link and not link.startswith("http"):
                                    link = self.base_url + link
                                link = link.replace("gateway_dep=YYZ", f"gateway_dep={self.DEPARTURE_CODE}")
                                link = link.replace("gateway_dep=YYX", f"gateway_dep={self.DEPARTURE_CODE}")

                            stars = 4
                            for line in lines:
                                if "star" in line.lower():
                                    nums = re.findall(r'\d', line)
                                    if nums and 1 <= int(nums[0]) <= 5:
                                        stars = int(nums[0])
                                        break

                            deal = self._make_deal(
                                destination=dest_code,
                                deal_type="package",
                                hotel_name=hotel_name,
                                hotel_stars=stars,
                                nights=nights,
                                price_per_person=price,
                                price_total=price * 2,
                                all_inclusive=1 if all_inclusive else 0,
                                direct_flight=0,
                                departure_airport=departure_airport,
                                url=link,
                                source_trip_id=f"sw_{dest_code}_{nights}n_{i}",
                            )
                            deals.append(deal)
                        except Exception as e:
                            self.log.debug("Sunwing card %d error: %s", i, e)
                            continue

                except Exception as e:
                    self.log.error("Sunwing scrape failed for %s: %s", page_path, e)
                    continue

            await browser.close()

        self.log.info("Sunwing: %d total deals (from %s)", len(deals), self.DEPARTURE_CODE)
        return deals

    def _guess_dest(self, text: str, override: str = None) -> str:
        if override:
            return override
        text_lower = text.lower()
        mapping = {
            "dominican": "DO", "punta cana": "DO", "cancun": "MX",
            "mexico": "MX", "jamaica": "JM", "montego": "JM",
            "cuba": "CU", "havana": "CU", "barbados": "BB",
            "costa rica": "CR", "puerto": "PR", "antigua": "AG",
            "saint lucia": "LC", "grenada": "GD",
        }
        for key, code in mapping.items():
            if key in text_lower:
                return code
        return "CARIBBEAN"
