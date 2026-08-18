import aiosqlite
from config import DB_PATH

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    destination TEXT NOT NULL,
    hotel_name TEXT,
    hotel_stars INTEGER,
    departure_date TEXT,
    return_date TEXT,
    nights INTEGER,
    price_per_person REAL,
    price_total REAL,
    currency TEXT DEFAULT 'CAD',
    all_inclusive INTEGER DEFAULT 0,
    direct_flight INTEGER DEFAULT 0,
    departure_airport TEXT DEFAULT 'YUL',
    url TEXT,
    fetched_at TEXT DEFAULT (datetime('now')),
    source_trip_id TEXT,
    UNIQUE(source, source_trip_id)
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_deals_dest ON deals(destination);
CREATE INDEX IF NOT EXISTS idx_deals_price ON deals(price_per_person);
CREATE INDEX IF NOT EXISTS idx_deals_source ON deals(source);
CREATE INDEX IF NOT EXISTS idx_deals_fetched ON deals(fetched_at);
"""


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    db = await get_db()
    await db.execute(CREATE_TABLE)
    await db.executescript(CREATE_INDEXES)
    await db.commit()
    await db.close()


async def upsert_deal(deal: dict):
    db = await get_db()
    await db.execute(
        """INSERT INTO deals (source, destination, hotel_name, hotel_stars,
            departure_date, return_date, nights, price_per_person, price_total,
            currency, all_inclusive, direct_flight, departure_airport, url, source_trip_id)
        VALUES (:source, :destination, :hotel_name, :hotel_stars,
            :departure_date, :return_date, :nights, :price_per_person, :price_total,
            :currency, :all_inclusive, :direct_flight, :departure_airport, :url, :source_trip_id)
        ON CONFLICT(source, source_trip_id) DO UPDATE SET
            price_per_person=excluded.price_per_person,
            price_total=excluded.price_total,
            fetched_at=datetime('now')
        """,
        deal,
    )
    await db.commit()
    await db.close()


async def search_deals(
    destination: str = None,
    min_stars: int = None,
    max_price: float = None,
    all_inclusive: bool = None,
    direct_only: bool = None,
    departure_airport: str = None,
    source: str = None,
) -> list[dict]:
    db = await get_db()
    query = "SELECT * FROM deals WHERE 1=1"
    params = []

    if destination:
        query += " AND destination = ?"
        params.append(destination)
    if min_stars:
        query += " AND hotel_stars >= ?"
        params.append(min_stars)
    if max_price:
        query += " AND price_per_person <= ?"
        params.append(max_price)
    if all_inclusive:
        query += " AND all_inclusive = 1"
    if direct_only:
        query += " AND direct_flight = 1"
    if departure_airport:
        query += " AND departure_airport = ?"
        params.append(departure_airport)
    if source:
        query += " AND source = ?"
        params.append(source)

    query += " ORDER BY price_per_person ASC"
    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in rows]


async def get_deal_count() -> int:
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) FROM deals")
    row = await cursor.fetchone()
    await db.close()
    return row[0]


async def get_last_refresh() -> str | None:
    db = await get_db()
    cursor = await db.execute("SELECT MAX(fetched_at) FROM deals")
    row = await cursor.fetchone()
    await db.close()
    return row[0] if row else None
