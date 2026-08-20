from scrapers.base import BaseScraper
from urllib.parse import urlencode
import re
import json
import asyncio


class RedtagScraper(BaseScraper):
    name = "redtag"
    base_url = "https://www.redtag.ca"
    booking_base = "https://secure-res.redtag.ca/vacations/search"

    def _build_booking_url(self, deal_data: dict) -> str:
        params = {
            "dest_dep": deal_data.get("DestinationID", ""),
            "sentdest": deal_data.get("Destination", ""),
            "gateway_dep": deal_data.get("DepartureCode", "YUL"),
            "remember_dep": deal_data.get("DepartureCity", "Montreal"),
            "date": deal_data.get("DepartureDate", ""),
            "duration": f"{deal_data.get('Duration', '7')}days",
            "dura_name": "7 or 8 Days",
            "numberOfRooms": 1,
            "numberOfAdults": 2,
            "numberOfChildren": 0,
            "all_inclusive": "y",
            "date_format": "Ymd",
            "hotel_no": deal_data.get("HotelID", ""),
            "alias": "engine",
            "sentalias": "api",
            "lang": "en",
        }
        return f"{self.booking_base}?{urlencode(params)}"

    async def _scrape_price_finder(self, page, booking_url: str, deal_template: dict) -> list[dict]:
        """Visit a booking URL and extract date-specific prices from the price finder carousel."""
        extra_deals = []
        try:
            await page.goto(booking_url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(12000)

            text = await page.inner_text("body")
            lines = [l.strip() for l in text.split("\n") if l.strip()]

            date_price_pairs = []
            i = 0
            while i < len(lines):
                date_match = re.match(
                    r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d+),(\d{4})$",
                    lines[i],
                )
                if date_match and i + 1 < len(lines):
                    price_match = re.search(r"\$([\d,]+)", lines[i + 1])
                    if price_match:
                        month_map = {
                            "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                            "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                            "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
                        }
                        mon = month_map.get(date_match.group(2), "01")
                        day = date_match.group(3).zfill(2)
                        year = date_match.group(4)
                        date_str = f"{year}-{mon}-{day}"
                        price = float(price_match.group(1).replace(",", ""))
                        if price > 100:
                            date_price_pairs.append((date_str, price))
                i += 1

            for date_str, price in date_price_pairs:
                source_id = f"rt_{deal_template['destination']}_{deal_template['nights']}n_{deal_template['hotel_name'][:30]}_{date_str}"
                deal = self._make_deal(
                    destination=deal_template["destination"],
                    deal_type="package",
                    hotel_name=deal_template["hotel_name"],
                    hotel_stars=deal_template["hotel_stars"],
                    departure_date=date_str,
                    nights=deal_template["nights"],
                    price_per_person=price,
                    price_total=price * 2,
                    all_inclusive=1,
                    direct_flight=0,
                    departure_airport=deal_template["departure_airport"],
                    url=booking_url,
                    source_trip_id=source_id,
                )
                extra_deals.append(deal)

            if date_price_pairs:
                self.log.info("Price finder %s: %d dates, prices $%.0f-$%.0f",
                    deal_template["hotel_name"][:25], len(date_price_pairs),
                    min(p for _, p in date_price_pairs), max(p for _, p in date_price_pairs))

        except Exception as e:
            self.log.debug("Price finder failed for %s: %s", deal_template.get("hotel_name", "?"), e)

        return extra_deals

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
        self.log.info("Searching RedTag Montreal for %s", destination or "all destinations")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.log.error("playwright not installed")
            return []

        deals = []
        pages = [
            f"{self.base_url}/vacation-packages/montreal/",
            f"{self.base_url}/deals/montreal/",
        ]

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            for page_url in pages:
                try:
                    await page.goto(page_url, timeout=30000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(8000)

                    cards = await page.query_selector_all(".rt-vacation-card")
                    self.log.info("RedTag %s: %d cards", page_url.split("/")[-2], len(cards))

                    for i, card in enumerate(cards):
                        try:
                            card_text = await card.inner_text()
                            lines = [l.strip() for l in card_text.split("\n") if l.strip()]

                            card_lower = card_text.lower()
                            if "toronto" in card_lower:
                                continue

                            title_el = await card.query_selector("a[title]")
                            hotel_name = ""
                            if title_el:
                                hotel_name = (await title_el.get_attribute("title") or "").strip()
                            if not hotel_name:
                                h3 = await card.query_selector("h3")
                                hotel_name = (await h3.inner_text()).strip() if h3 else ""

                            original_price = 0
                            sale_price = 0
                            savings_pct = 0

                            for line in lines:
                                m = re.search(r"was\s*\$([\d,]+)", line, re.IGNORECASE)
                                if m:
                                    original_price = float(m.group(1).replace(",", ""))

                                m2 = re.search(r"Save\s+(\d+)%", line, re.IGNORECASE)
                                if m2:
                                    savings_pct = int(m2.group(1))

                                m3 = re.match(r"^\$([\d,]+)$", line.strip())
                                if m3:
                                    val = float(m3.group(1).replace(",", ""))
                                    if val > 100:
                                        sale_price = val

                            if sale_price <= 0:
                                for line in lines:
                                    m = re.search(r"\$([\d,]+)", line)
                                    if m:
                                        val = float(m.group(1).replace(",", ""))
                                        if 100 < val != original_price:
                                            sale_price = val
                                            break

                            if sale_price <= 0:
                                continue

                            link = ""
                            deal_data = {}
                            departure_date = ""
                            btn = await card.query_selector("button[data-deal]")
                            if btn:
                                deal_json_str = await btn.get_attribute("data-deal")
                                if deal_json_str:
                                    try:
                                        deal_data = json.loads(deal_json_str)
                                        link = self._build_booking_url(deal_data)
                                        raw_date = deal_data.get("DepartureDate", "")
                                        if raw_date and len(raw_date) == 8:
                                            departure_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
                                    except (json.JSONDecodeError, KeyError):
                                        pass

                            if not link:
                                all_links = await card.query_selector_all("a[href]")
                                for a in all_links:
                                    href = await a.get_attribute("href") or ""
                                    if "/hotel-resorts/" in href:
                                        if not href.startswith("http"):
                                            href = self.base_url + href
                                        link = href
                                        break

                            stars = 4
                            stars_match = re.search(r"(\d\.\d)\s+out\s+of\s+5", card_text)
                            if stars_match:
                                stars = int(float(stars_match.group(1)))

                            card_dest = "CARIBBEAN"
                            dest_guess = {
                                "dominican": "DO", "punta cana": "DO", "samana": "DO",
                                "cancun": "MX", "mexico": "MX", "riviera maya": "MX",
                                "jamaica": "JM", "montego bay": "JM", "cuba": "CU",
                                "barbados": "BB", "costa rica": "CR", "antigua": "AG",
                                "saint lucia": "LC", "puerto plata": "DO",
                            }
                            for key, code in dest_guess.items():
                                if key in card_lower:
                                    card_dest = code
                                    break

                            nights = 7
                            nights_match = re.search(r"(\d+)\s+days", card_text, re.IGNORECASE)
                            if nights_match:
                                nights = max(int(nights_match.group(1)) - 1, 3)

                            source_id = f"rt_{card_dest}_{nights}n_{hotel_name[:30]}_{departure_date or i}"

                            deal = self._make_deal(
                                destination=card_dest,
                                deal_type="package",
                                hotel_name=hotel_name,
                                hotel_stars=stars,
                                departure_date=departure_date,
                                nights=nights,
                                price_per_person=sale_price,
                                price_total=sale_price * 2,
                                all_inclusive=1 if all_inclusive else 0,
                                direct_flight=0,
                                departure_airport=departure_airport,
                                url=link,
                                source_trip_id=source_id,
                            )
                            deal["original_price"] = original_price
                            deal["savings_pct"] = savings_pct
                            deals.append(deal)

                        except Exception as e:
                            self.log.debug("RedTag card error: %s", e)
                            continue

                except Exception as e:
                    self.log.error("RedTag page %s failed: %s", page_url, e)
                    continue

            unique_hotels = {}
            for d in deals:
                if d.get("url") and "secure-res" in d["url"] and d["hotel_name"]:
                    key = (d["hotel_name"], d["destination"], d["nights"])
                    if key not in unique_hotels:
                        unique_hotels[key] = d
            cheapest = sorted(unique_hotels.values(), key=lambda x: x["price_per_person"])[:20]
            unique_hotels = {(d["hotel_name"], d["destination"], d["nights"]): d for d in cheapest}

            self.log.info("Price finder: visiting %d unique hotel booking URLs", len(unique_hotels))
            finder_deals = []
            for (hotel_name, dest, nights), template in unique_hotels.items():
                extra = await self._scrape_price_finder(page, template["url"], template)
                finder_deals.extend(extra)
                await asyncio.sleep(2)

            await browser.close()

        all_deals = deals + finder_deals
        self.log.info("RedTag: %d card deals + %d price-finder dates = %d total",
            len(deals), len(finder_deals), len(all_deals))
        return all_deals
