from scrapers.sunwing import SunwingScraper
from scrapers.air_transat import AirTransatScraper
from scrapers.westjet import WestJetScraper
from scrapers.expedia import ExpediaScraper
from scrapers.booking import BookingScraper
from scrapers.redtag import RedtagScraper

PACKAGE_SCRAPERS = [
    RedtagScraper(),
    SunwingScraper(),
    AirTransatScraper(),
    WestJetScraper(),
]

HOTEL_SCRAPERS = [
    BookingScraper(),
    ExpediaScraper(),
]

ALL_SCRAPERS = PACKAGE_SCRAPERS + HOTEL_SCRAPERS

__all__ = ["ALL_SCRAPERS", "PACKAGE_SCRAPERS", "HOTEL_SCRAPERS"]
