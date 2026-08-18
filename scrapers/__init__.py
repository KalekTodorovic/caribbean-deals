from scrapers.sunwing import SunwingScraper
from scrapers.air_transat import AirTransatScraper
from scrapers.westjet import WestJetScraper
from scrapers.expedia import ExpediaScraper
from scrapers.booking import BookingScraper

ALL_SCRAPERS = [
    SunwingScraper(),
    AirTransatScraper(),
    WestJetScraper(),
    ExpediaScraper(),
    BookingScraper(),
]

__all__ = ["ALL_SCRAPERS"]
