from abc import ABC, abstractmethod
import logging

log = logging.getLogger("scrapers")


class BaseScraper(ABC):
    name: str = "base"
    base_url: str = ""

    def __init__(self):
        self.log = logging.getLogger(f"scrapers.{self.name}")

    @abstractmethod
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
        """Search for deals. Returns list of deal dicts with keys:
        source, destination, hotel_name, hotel_stars, departure_date,
        return_date, nights, price_per_person, price_total, currency,
        all_inclusive, direct_flight, departure_airport, url, source_trip_id
        """
        pass

    def _make_deal(self, **kwargs) -> dict:
        defaults = {
            "source": self.name,
            "destination": "",
            "deal_type": "hotel",
            "hotel_name": "",
            "hotel_stars": 0,
            "departure_date": "",
            "return_date": "",
            "nights": 0,
            "price_per_person": 0.0,
            "price_total": 0.0,
            "original_price": 0.0,
            "savings_pct": 0,
            "currency": "CAD",
            "all_inclusive": 0,
            "direct_flight": 0,
            "departure_airport": "YUL",
            "url": "",
            "source_trip_id": "",
        }
        defaults.update(kwargs)
        return defaults
