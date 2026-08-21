# Caribbean Deals - Technical Reference

## RedTag Booking URLs (CRITICAL)

RedTag card pages (`/vacation-packages/montreal/`, `/deals/montreal/`) show deal cards.
Each card has a `button[data-deal]` attribute containing JSON with all booking params.

**URL pattern:**
```
https://secure-res.redtag.ca/vacations/search?dest_dep={DestinationID}&sentdest={Destination}&gateway_dep=YUL&remember_dep=Montreal&date={DepartureDate}&duration={Duration}days&dura_name=7+or+8+Days&numberOfRooms=1&numberOfAdults=2&numberOfChildren=0&all_inclusive=y&date_format=Ymd&hotel_no={HotelID}&alias=engine&sentalias=api&lang=en
```

**Key data-deal JSON fields:**
- `DestinationID`, `Destination` (e.g. 10, "Punta Cana")
- `DepartureCode` = "YUL" (Montreal)
- `DepartureDate` = "YYYYMMDD" format
- `Duration` = 7
- `HotelID` = hotel number
- `Hotel` = full hotel name (e.g. "Bahia Principe Luxury Runaway Bay")

**URL builder source:** `app.js` on redtag.ca contains `fe.A("https://secure-res.redtag.ca/vacations/search")` that builds these URLs.

**CRITICAL: `sentdest` must use hotel name, not just destination!**
- WRONG: `sentdest=Runaway+Bay` (just destination) — returns 0 results
- RIGHT: `sentdest=Bahia+Principe+Luxury+Runaway+Bay+-+Runaway+Bay` (Hotel + Destination)
- The `Hotel` field from data-deal is the correct value. Build as `{Hotel} - {Destination}`.

**Booking engine price finder:** When visiting a booking URL, the page shows a carousel of 7 nearby dates with "From $X" prices. This is scraped in `_scrape_price_finder()` for multi-date comparison.

**RedTag price calendar CSS (CRITICAL):**
- Each date is a `<div class="col best-price day">` (or with extra classes)
- Price is `<span class="price">From$1,699</span>`
- **`cheapest` class** on the day div = RedTag's own "best price" indicator. Use this to flag deals.
- **Red color** `rgb(202, 0, 0)` on `<span class="price">` = currently selected date (not necessarily cheapest)
- The `cheapest` class is the reliable indicator, not the color.

**IMPORTANT:** The booking engine (`secure-res.redtag.ca`) always returns Montreal prices when `gateway_dep=YUL`. It does NOT work with hotel-resort category links from `redtag.ca/deals/`. Only the `secure-res.redtag.ca` URLs produce Montreal-specific pricing.

## RedTag Scraping Flow

1. Scrape cards from 2 pages (`/vacation-packages/montreal/`, `/deals/montreal/`)
2. Extract `button[data-deal]` JSON from each card
3. Build `secure-res.redtag.ca` booking URL from JSON
4. Skip cards without `button[data-deal]` (no fallback - fallback gives bad category URLs)
5. For top 20 cheapest hotels, visit booking URL and scrape price finder carousel (7 dates each)

## Sunwing

Deprecated in favor of RedTag. Uses Gatsby SPA. Booking engine has DataDome CAPTCHA.
Prices are always Toronto-based. Do NOT use.

## Booking.com

Works with Playwright. Cards: `[data-testid="property-card"]`.
Must scroll 3x for lazy loading. Real CAD prices.
Departure date must be in URL params.

## Expedia

Works with Playwright. Scrapes `/search` page.

## DB Schema Notes

- `departure_date`: YYYY-MM-DD format. Empty for Booking.com (no date in scrape).
- `original_price`: Was-price from RedTag cards.
- `savings_pct`: Save % from RedTag cards.
- `source_trip_id`: Format `rt_{dest}_{nights}n_{hotel}__{date}` for RedTag. Includes date so same hotel on different dates gets unique rows.
- `url`: Must be `secure-res.redtag.ca` booking URL for RedTag deals. Never use `/deals/montreal/` links.
- `operator`: Tour operator name (e.g. "Transat", "Air Canada Vacations"). Populated from card text + booking engine page text matching.

## RedTag Tour Operators

Known operators (from booking engine filter sidebar):
- Air Canada Vacations, Caribe Sol, Club Med, Hola Sun, Sunquest
- Sunwing Vacations, TravelBrands, Transat, WestJet Vacations, WestJet Vacations Quebec

The `/engine/vacations` API response contains `filter.tour_operator` mapping codes (VAC, CAH, etc.) to display names. Operator is extracted by matching these names against page body text during price finder.

## Environment

- **Timezone:** ET (UTC-4). Local time = ET time.
- **Playwright:** Must run outside uvicorn reload mode (Windows subprocess error). `reload=False` in main.py.
- **DB path:** `data/deals.db`
- **Server:** `localhost:8000`
