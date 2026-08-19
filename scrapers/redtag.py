from scrapers.base import BaseScraper
import re


class RedtagScraper(BaseScraper):
    name = "redtag"
    base_url = "https://www.redtag.ca"

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
                            all_links = await card.query_selector_all("a[href]")
                            for a in all_links:
                                href = await a.get_attribute("href") or ""
                                if "/hotel-resorts/" in href:
                                    if not href.startswith("http"):
                                        href = self.base_url + href
                                    link = href
                                    break
                            if not link:
                                for a in all_links:
                                    href = await a.get_attribute("href") or ""
                                    if href and "/deals/" not in href and "transat" not in href and "aircanada" not in href:
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

                            source_id = f"rt_{card_dest}_{nights}n_{hotel_name[:20]}_{i}"

                            deal = self._make_deal(
                                destination=card_dest,
                                deal_type="package",
                                hotel_name=hotel_name,
                                hotel_stars=stars,
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

            await browser.close()

        self.log.info("RedTag: %d Montreal deals", len(deals))
        return deals
