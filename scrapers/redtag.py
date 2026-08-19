from scrapers.base import BaseScraper
import re
import json


class RedtagScraper(BaseScraper):
    name = "redtag"
    base_url = "https://www.redtag.ca"
    DEPARTURE_CODES = "yul,ymq"

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
        self.log.info("Searching RedTag for %s (from %s)", destination or "all destinations", departure_airport)
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.log.error("playwright not installed")
            return []

        deals = []
        dest_map = {
            "DO": "Dominican Republic", "MX": "Mexico", "CU": "Cuba",
            "JM": "Jamaica", "BB": "Barbados", "CR": "Costa Rica",
            "AG": "Antigua", "LC": "Saint Lucia",
        }

        dest_name = dest_map.get(destination, "") if destination else ""

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
            )

            await context.add_cookies([{
                "name": "rt_gateway",
                "value": self.DEPARTURE_CODES,
                "domain": ".redtag.ca",
                "path": "/"
            }])

            page = await context.new_page()

            try:
                await page.goto(f"{self.base_url}/vacation-packages/", timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(6000)

                # Set departure to Montreal
                selects = await page.query_selector_all("select")
                for sel in selects:
                    txt = await sel.inner_text()
                    if "toronto" in txt.lower() or "montreal" in txt.lower():
                        options = await sel.query_selector_all("option")
                        for opt in options:
                            otxt = (await opt.inner_text()).strip()
                            if "montreal" in otxt.lower():
                                val = await opt.get_attribute("value") or ""
                                await sel.select_option(value=val)
                                self.log.info("Set departure to Montreal: %s", val)
                                break
                        break

                await page.wait_for_timeout(500)

                # Set destination if specified
                if dest_name:
                    for sel in selects:
                        options = await sel.query_selector_all("option")
                        for opt in options:
                            otxt = (await opt.inner_text()).strip()
                            if dest_name.lower() in otxt.lower():
                                val = await opt.get_attribute("value") or ""
                                await sel.select_option(value=val)
                                self.log.info("Set destination to %s: %s", dest_name, val)
                                break
                        else:
                            continue
                        break

                await page.wait_for_timeout(500)

                # Set duration to 7 days
                for sel in selects:
                    txt = await sel.inner_text()
                    if "days" in txt.lower():
                        options = await sel.query_selector_all("option")
                        for opt in options:
                            otxt = (await opt.inner_text()).strip()
                            if "7" in otxt:
                                val = await opt.get_attribute("value") or ""
                                await sel.select_option(value=val)
                                break
                        break

                await page.wait_for_timeout(500)

                # Click Search - close any open calendar first
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(500)

                search_btn = await page.query_selector('button.search-btn:has-text("Search Now")')
                if search_btn:
                    await search_btn.click(force=True)
                    self.log.info("Clicked Search Now")
                    await page.wait_for_timeout(15000)

                # Scrape rt-vacation-card elements
                cards = await page.query_selector_all('.rt-vacation-card')
                self.log.info("RedTag: found %d vacation cards", len(cards))

                for i, card in enumerate(cards[:30]):
                    try:
                        card_text = await card.inner_text()
                        lines = [l.strip() for l in card_text.split("\n") if l.strip()]

                        # Extract hotel name from title attribute
                        title_el = await card.query_selector("a[title]")
                        hotel_name = ""
                        if title_el:
                            hotel_name = (await title_el.get_attribute("title") or "").strip()
                        if not hotel_name:
                            h3 = await card.query_selector("h3")
                            hotel_name = (await h3.inner_text()).strip() if h3 else f"RedTag Hotel {i+1}"

                        # Extract prices
                        original_price = 0
                        sale_price = 0
                        savings_pct = 0

                        for line in lines:
                            m = re.search(r'was\s*\$([\d,]+)', line, re.IGNORECASE)
                            if m:
                                original_price = float(m.group(1).replace(',', ''))

                            m2 = re.search(r'Save\s+(\d+)%', line, re.IGNORECASE)
                            if m2:
                                savings_pct = int(m2.group(1))

                            m3 = re.match(r'^\$([\d,]+)$', line.strip())
                            if m3:
                                val = float(m3.group(1).replace(',', ''))
                                if val > 100:
                                    sale_price = val

                        if sale_price <= 0:
                            for line in lines:
                                m = re.search(r'\$([\d,]+)', line)
                                if m:
                                    val = float(m.group(1).replace(',', ''))
                                    if val > 100 and val != original_price:
                                        sale_price = val
                                        break

                        if sale_price <= 0:
                            continue

                        # Get link
                        link = ""
                        el = await card.query_selector("a[href]")
                        if el:
                            link = await el.get_attribute("href") or ""
                            if link and not link.startswith("http"):
                                link = self.base_url + link

                        # Guess destination from card text
                        card_dest = "CARIBBEAN"
                        card_lower = card_text.lower()
                        dest_guess = {
                            "dominican": "DO", "punta cana": "DO", "cancun": "MX",
                            "mexico": "MX", "jamaica": "JM", "cuba": "CU",
                            "barbados": "BB", "costa rica": "CR", "antigua": "AG",
                            "saint lucia": "LC",
                        }
                        for key, code in dest_guess.items():
                            if key in card_lower:
                                card_dest = code
                                break

                        deal = self._make_deal(
                            destination=card_dest,
                            deal_type="package",
                            hotel_name=hotel_name,
                            hotel_stars=4,
                            nights=7,
                            price_per_person=sale_price,
                            price_total=sale_price * 2,
                            all_inclusive=1 if all_inclusive else 0,
                            direct_flight=0,
                            departure_airport=departure_airport,
                            url=link,
                            source_trip_id=f"rt_{card_dest}_{i}",
                        )
                        deal["original_price"] = original_price
                        deal["savings_pct"] = savings_pct
                        deals.append(deal)

                    except Exception as e:
                        self.log.debug("RedTag card %d error: %s", i, e)
                        continue

            except Exception as e:
                self.log.error("RedTag scrape failed: %s", e)
            finally:
                await browser.close()

        self.log.info("RedTag: %d total deals (from Montreal)", len(deals))
        return deals
