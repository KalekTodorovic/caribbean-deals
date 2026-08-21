import asyncio
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import (
    DEPARTURE_AIRPORTS,
    DESTINATIONS,
    REFRESH_INTERVAL_HOURS,
    STAR_RATINGS,
    TOUR_OPERATORS,
)
from models import (
    find_outliers,
    get_deal_count,
    get_deal_count_by_type,
    get_last_refresh,
    get_operators,
    init_db,
    search_deals,
    upsert_deal,
)
from scrapers import ALL_SCRAPERS, PACKAGE_SCRAPERS, HOTEL_SCRAPERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
log = logging.getLogger("main")

scheduler = AsyncIOScheduler()
_scrape_lock = asyncio.Lock()

PACKAGE_NIGHTS_OPTIONS = [7, 10, 14]


async def run_all_scrapers():
    if _scrape_lock.locked():
        log.info("Scrape already in progress, skipping")
        return
    async with _scrape_lock:
        all_scrapers = ALL_SCRAPERS
        log.info("Starting scheduled scrape of %d sources", len(all_scrapers))

        for scraper in PACKAGE_SCRAPERS:
            try:
                deals = await scraper.search(all_inclusive=True, direct_only=False)
                for deal in deals:
                    await upsert_deal(deal)
                log.info("%s (package): saved %d deals", scraper.name, len(deals))
            except Exception as e:
                log.error("Scraper %s failed: %s", scraper.name, e)

        for scraper in HOTEL_SCRAPERS:
            try:
                deals = await scraper.search(all_inclusive=False, direct_only=False)
                for deal in deals:
                    await upsert_deal(deal)
                log.info("%s (hotel): saved %d deals", scraper.name, len(deals))
            except Exception as e:
                log.error("Scraper %s failed: %s", scraper.name, e)

        count = await get_deal_count()
        log.info("Scrape complete. Total deals in DB: %d", count)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    log.info("Database initialized")
    scheduler.add_job(run_all_scrapers, "interval", hours=REFRESH_INTERVAL_HOURS, id="refresh")
    scheduler.start()
    log.info("Scheduler started (refresh every %dh)", REFRESH_INTERVAL_HOURS)
    asyncio.create_task(run_all_scrapers())
    yield
    scheduler.shutdown()


app = FastAPI(title="Caribbean Deal Finder", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    counts = await get_deal_count_by_type()
    last = await get_last_refresh()

    package_deals = await search_deals(deal_type="package", sort_by="deal_score")
    hotel_deals = await search_deals(deal_type="hotel")

    return templates.TemplateResponse(request, "index.html", {
        "airports": DEPARTURE_AIRPORTS,
        "destinations": DESTINATIONS,
        "star_ratings": STAR_RATINGS,
        "package_count": counts.get("package", 0),
        "hotel_count": counts.get("hotel", 0),
        "deal_count": sum(counts.values()),
        "last_refresh": last,
        "package_deals": package_deals[:20],
        "hotel_deals": hotel_deals[:20],
        "package_nights_options": PACKAGE_NIGHTS_OPTIONS,
    })


@app.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    destination: str = Query(None),
    departure_airport: str = Query(None),
    max_price: str = Query(None),
    min_stars: str = Query(None),
    all_inclusive: str = Query(None),
    direct_only: str = Query(None),
    source: str = Query(None),
    deal_type: str = Query(None),
    nights: str = Query(None),
    sort_by: str = Query(None),
    operator: str = Query(None),
):
    max_price_f = float(max_price) if max_price else None
    if min_stars is None:
        min_stars_f = 4.5
    elif min_stars == "0":
        min_stars_f = None
    else:
        min_stars_f = float(min_stars)
    ai = all_inclusive == "true" if all_inclusive else None
    direct = direct_only == "true" if direct_only else None
    nights_list = [int(n) for n in nights.split(",") if n.strip()] if nights else None

    deals = await search_deals(
        destination=destination or None,
        min_stars=min_stars_f,
        max_price=max_price_f,
        all_inclusive=ai,
        direct_only=direct,
        departure_airport=departure_airport or None,
        source=source or None,
        deal_type=deal_type or None,
        nights=nights_list,
        operator=operator or None,
        sort_by=sort_by or "price",
    )
    db_operators = await get_operators()
    all_operators = sorted(set(list(TOUR_OPERATORS.values()) + db_operators))
    return templates.TemplateResponse(request, "results.html", {
        "deals": deals,
        "airports": DEPARTURE_AIRPORTS,
        "destinations": DESTINATIONS,
        "star_ratings": STAR_RATINGS,
        "deal_type": deal_type,
        "package_nights_options": PACKAGE_NIGHTS_OPTIONS,
        "db_operators": all_operators,
        "tour_operators": TOUR_OPERATORS,
        "filters": {
            "destination": destination,
            "departure_airport": departure_airport,
            "max_price": max_price,
            "min_stars": min_stars,
            "all_inclusive": all_inclusive,
            "direct_only": direct_only,
            "source": source,
            "deal_type": deal_type,
            "nights": nights,
            "sort_by": sort_by,
            "operator": operator,
        },
    })


@app.api_route("/scrape", methods=["GET", "POST"])
async def trigger_scrape():
    asyncio.create_task(run_all_scrapers())
    return RedirectResponse("/", status_code=303)


@app.get("/outliers", response_class=HTMLResponse)
async def outliers_page(request: Request):
    outlier_deals = await find_outliers(min_datapoints=2, threshold_pct=15)
    return templates.TemplateResponse(request, "outliers.html", {
        "outliers": outlier_deals,
        "count": len(outlier_deals),
    })


@app.get("/api/outliers")
async def api_outliers(min_datapoints: int = Query(2), threshold_pct: int = Query(15)):
    return await find_outliers(min_datapoints=min_datapoints, threshold_pct=threshold_pct)


@app.get("/api/deals")
async def api_deals(
    destination: str = Query(None),
    max_price: float = Query(None),
    min_stars: int = Query(None),
    all_inclusive: bool = Query(None),
    deal_type: str = Query(None),
    nights: str = Query(None),
    operator: str = Query(None),
):
    nights_list = [int(n) for n in nights.split(",") if n.strip()] if nights else None
    return await search_deals(
        destination=destination,
        min_stars=min_stars,
        max_price=max_price,
        all_inclusive=all_inclusive,
        deal_type=deal_type,
        nights=nights_list,
        operator=operator,
    )


@app.get("/api/stats")
async def api_stats():
    return {
        "total_deals": await get_deal_count(),
        "last_refresh": await get_last_refresh(),
        "sources": [s.name for s in ALL_SCRAPERS],
    }


if __name__ == "__main__":
    import uvicorn
    from config import HOST, PORT
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
