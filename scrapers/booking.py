from scrapers.base import BaseScraper
import re
from datetime import datetime, timedelta


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
        dest_searches = {
            "CU": "Havana Cuba", "DO": "Punta Cana Dominican Republic",
            "MX": "Cancun Mexico", "JM": "Montego Bay Jamaica",
            "HT": "Port-au-Prince Haiti", "BB": "Barbados",
            "AG": "St John's Antigua", "LC": "Castries Saint Lucia",
            "CR": "San Jose Costa Rica", "PA": "Panama City Panama",
            "PR": "San Juan Puerto Rico", "CO": "Cartagena Colombia",
        }

        if destination:
            search_list = [(destination, dest_searches.get(destination, "Caribbean"))]
        else:
            search_list = [
                ("DO", "Punta Cana Dominican Republic"),
                ("MX", "Cancun Mexico"),
                ("JM", "Montego Bay Jamaica"),
                ("CU", "Havana Cuba"),
                ("BB", "Barbados"),
                ("CR", "San Jose Costa Rica"),
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
                        f"{self.base_url}/searchresults.html"
                        f"?ss={search_term.replace(' ', '+')}"
                        f"&checkin={checkin}"
                        f"&checkout={checkout}"
                        f"&group_adults=2"
                        f"&no_rooms=1"
                        f"&selected_currency=CAD"
                    )
                    self.log.info("Booking URL: %s", url)
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(5000)
                    for _ in range(3):
                        await page.evaluate("window.scrollBy(0, 800)")
                        await page.wait_for_timeout(2000)

                    cards = await page.query_selector_all('[data-testid="property-card"]')
                    self.log.info("Booking %s: found %d cards", dest_code, len(cards))

                    for i, card in enumerate(cards[:25]):
                        try:
                            card_text = await card.inner_text()
                            lines = [l.strip() for l in card_text.split("\n") if l.strip()]

                            title = ""
                            for line in lines:
                                if any(kw in line.lower() for kw in ["hotel", "resort", "inn", "suit", "villa", "apartment", "hostal", "rio", "riu", "palace", "all inclusive"]):
                                    if 3 < len(line) < 100:
                                        title = line
                                        break
                            if not title:
                                for line in lines:
                                    if 5 < len(line) < 80 and "score" not in line.lower() and "review" not in line.lower() and "cancel" not in line.lower():
                                        title = line
                                        break
                            if not title:
                                title = f"Booking Hotel {i+1}"

                            price = 0
                            for line in lines:
                                price_match = re.search(r'CAD[\$\s]*([\d,]+)', line)
                                if price_match:
                                    val = float(price_match.group(1).replace(',', ''))
                                    if val > 10:
                                        price = val
                                        break

                            if price <= 0:
                                for line in lines:
                                    dollar_match = re.search(r'\$([\d,]+)', line)
                                    if dollar_match:
                                        val = float(dollar_match.group(1).replace(',', ''))
                                        if val > 10:
                                            price = val
                                            break

                            if price <= 0:
                                continue

                            stars = 4
                            for line in lines:
                                star_match = re.search(r'(\d)\s*star', line, re.IGNORECASE)
                                if star_match:
                                    s = int(star_match.group(1))
                                    if 1 <= s <= 5:
                                        stars = s
                                        break

                            link = ""
                            el = await card.query_selector('a[href*="hotel"]') or await card.query_selector("a[href]")
                            if el:
                                link = await el.get_attribute("href") or ""
                                if link and not link.startswith("http"):
                                    link = self.base_url + link

                            is_ai = any("all-inclusive" in l.lower() or "all inclusive" in l.lower() for l in lines)

                            deal = self._make_deal(
                                destination=dest_code,
                                deal_type="hotel",
                                hotel_name=title,
                                hotel_stars=stars,
                                nights=7,
                                price_per_person=price,
                                price_total=price * 2,
                                all_inclusive=1 if is_ai else 0,
                                direct_flight=0,
                                departure_airport=departure_airport,
                                url=link,
                                source_trip_id=f"bk_{dest_code}_{checkin}_{i}",
                            )
                            deals.append(deal)
                        except Exception as e:
                            self.log.debug("Booking card %d error: %s", i, e)
                            continue

                except Exception as e:
                    self.log.error("Booking scrape failed for %s: %s", dest_code, e)
                    continue

            await browser.close()

        self.log.info("Booking: %d total deals", len(deals))
        return deals
