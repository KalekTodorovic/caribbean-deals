import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "deals.db"

PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

REFRESH_INTERVAL_HOURS = 4

DEPARTURE_AIRPORTS = {
    "YUL": "Montréal–Trudeau (YUL)",
    "YMX": "Montréal–Mirabel (YMX)",
}

DESTINATIONS = {
    "CU": "Cuba",
    "DO": "Dominican Republic",
    "MX": "Mexico",
    "JM": "Jamaica",
    "HT": "Haiti",
    "PR": "Puerto Rico",
    "BB": "Barbados",
    "AG": "Antigua",
    "LC": "Saint Lucia",
    "VC": "St. Vincent",
    "GD": "Grenada",
    "TT": "Trinidad & Tobago",
    "BZ": "Belize",
    "CR": "Costa Rica",
    "PA": "Panama",
    "CO": "Colombia",
}

STAR_RATINGS = [3, 4, 5]

TOUR_OPERATORS = {
    "VAC": "Air Canada Vacations",
    "CAH": "Caribe Sol",
    "CLM": "Club Med",
    "HOL": "Hola Sun",
    "SQV": "Sunquest",
    "SWG": "Sunwing Vacations",
    "TBA": "TravelBrands",
    "VAT": "Transat",
    "WJS": "WestJet Vacations",
    "VWQ": "WestJet Vacations Quebec",
}
