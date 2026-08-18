import asyncio
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import (
    DEPARTURE_AIRPORTS,
    DESTINATIONS,
    REFRESH_INTERVAL_HOURS,
    STAR_RATINGS,
)
from models import get_deal_count, get_last_refresh, init_db, search_deals, upsert_deal
from scrapers import ALL_SCRAPERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
log = logging.getLogger("main")

scheduler = AsyncIOScheduler()
_scrape_lock = asyncio.Lock()


async def run_all_scrapers():
    if _scrape_lock.locked():
        log.info("Scrape already in progress, skipping")
        return
    async with _scrape_lock:
        log.info("Starting scheduled scrape of %d sources", len(ALL_SCRAPERS))
        for scraper in ALL_SCRAPERS:
            try:
                deals = await scraper.search(
                    all_inclusive=True,
                    direct_only=False,
                )
                for deal in deals:
                    await upsert_deal(deal)
                log.info("%s: saved %d deals", scraper.name, len(deals))
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
    count = await get_deal_count()
    last = await get_last_refresh()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "airports": DEPARTURE_AIRPORTS,
        "destinations": DESTINATIONS,
        "star_ratings": STAR_RATINGS,
        "deal_count": count,
        "last_refresh": last,
    })


@app.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    destination: str = Query(None),
    departure_airport: str = Query(None),
    max_price: float = Query(None),
    min_stars: int = Query(None),
    all_inclusive: bool = Query(None),
    direct_only: bool = Query(None),
    source: str = Query(None),
):
    deals = await search_deals(
        destination=destination,
        min_stars=min_stars,
        max_price=max_price,
        all_inclusive=all_inclusive,
        direct_only=direct_only,
        departure_airport=departure_airport,
        source=source,
    )
    return templates.TemplateResponse("results.html", {
        "request": request,
        "deals": deals,
        "airports": DEPARTURE_AIRPORTS,
        "destinations": DESTINATIONS,
        "star_ratings": STAR_RATINGS,
        "filters": {
            "destination": destination,
            "departure_airport": departure_airport,
            "max_price": max_price,
            "min_stars": min_stars,
            "all_inclusive": all_inclusive,
            "direct_only": direct_only,
            "source": source,
        },
    })


@app.post("/scrape")
async def trigger_scrape():
    asyncio.create_task(run_all_scrapers())
    return RedirectResponse("/", status_code=303)


@app.get("/api/deals")
async def api_deals(
    destination: str = Query(None),
    max_price: float = Query(None),
    min_stars: int = Query(None),
    all_inclusive: bool = Query(None),
):
    return await search_deals(
        destination=destination,
        min_stars=min_stars,
        max_price=max_price,
        all_inclusive=all_inclusive,
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
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
