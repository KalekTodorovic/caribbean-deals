from scrapers.base import BaseScraper


class BookingScraper(BaseScraper):
    name = "booking"
    base_url = "https://www.booking.com"

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
        self.log.info("Searching Booking.com for %s", destination or "all destinations")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.log.error("playwright not installed")
            return []

        deals = []
        dest_names = {
            "CU": "Havana", "DO": "Punta Cana", "MX": "Cancun",
            "JM": "Montego Bay", "BB": "Bridgetown", "AG": "St John's",
            "LC": "Castries", "CR": "San Jose", "PA": "Panama City",
        }
        dest_name = dest_names.get(destination, "Caribbean") if destination else "Caribbean"

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            try:
                url = f"{self.base_url}/searchresults.html?ss={dest_name}&checkin=2026-09-01&checkout=2026-09-08&group_adults=2&no_rooms=1&selected_currency=CAD"
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(5000)

                cards = await page.query_selector_all('[data-testid="property-card"], .sr_property_block, [class*="property"]')
                self.log.info("Found %d cards on Booking.com", len(cards))

                for i, card in enumerate(cards[:50]):
                    try:
                        title_el = await card.query_selector('[data-testid="title"], .sr-hotel__name, h3, [class*="name"]')
                        title = await title_el.inner_text() if title_el else f"Booking Hotel {i+1}"

                        price_el = await card.query_selector('[data-testid="price-and-discounted-price"], [class*="price"], .bui-price-display__value')
                        price_text = await price_el.inner_text() if price_el else "0"
                        price = self._parse_price(price_text)

                        stars_el = await card.query_selector('[class*="star"], [aria-label*="star"]')
                        stars_text = await stars_el.get_attribute('aria-label') if stars_el else "4"
                        stars = self._parse_stars(stars_text or "4")

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
                            direct_flight=0,
                            departure_airport=departure_airport,
                            url=link,
                            source_trip_id=f"bk_{i}_{destination or 'all'}",
                        )
                        if price > 0:
                            deals.append(deal)
                    except Exception as e:
                        self.log.debug("Failed to parse card %d: %s", i, e)
                        continue

            except Exception as e:
                self.log.error("Booking scrape failed: %s", e)
            finally:
                await browser.close()

        self.log.info("Booking: %d deals found", len(deals))
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
