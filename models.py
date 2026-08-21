import aiosqlite
from config import DB_PATH

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    destination TEXT NOT NULL,
    deal_type TEXT DEFAULT 'hotel',
    hotel_name TEXT,
    hotel_stars INTEGER,
    departure_date TEXT,
    return_date TEXT,
    nights INTEGER,
    price_per_person REAL,
    price_total REAL,
    original_price REAL DEFAULT 0,
    savings_pct INTEGER DEFAULT 0,
    currency TEXT DEFAULT 'CAD',
    all_inclusive INTEGER DEFAULT 0,
    direct_flight INTEGER DEFAULT 0,
    departure_airport TEXT DEFAULT 'YUL',
    url TEXT,
    fetched_at TEXT DEFAULT (datetime('now')),
    source_trip_id TEXT,
    operator TEXT DEFAULT '',
    UNIQUE(source, source_trip_id)
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_deals_dest ON deals(destination);
CREATE INDEX IF NOT EXISTS idx_deals_price ON deals(price_per_person);
CREATE INDEX IF NOT EXISTS idx_deals_source ON deals(source);
CREATE INDEX IF NOT EXISTS idx_deals_fetched ON deals(fetched_at);
CREATE INDEX IF NOT EXISTS idx_deals_type ON deals(deal_type);
CREATE INDEX IF NOT EXISTS idx_deals_nights ON deals(nights);
"""


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    db = await get_db()
    await db.execute(CREATE_TABLE)
    await db.executescript(CREATE_INDEXES)
    try:
        await db.execute("ALTER TABLE deals ADD COLUMN operator TEXT DEFAULT ''")
    except Exception:
        pass
    await db.commit()
    await db.close()


async def upsert_deal(deal: dict):
    db = await get_db()
    await db.execute(
        """INSERT INTO deals (source, destination, deal_type, hotel_name, hotel_stars,
            departure_date, return_date, nights, price_per_person, price_total,
            original_price, savings_pct,
            currency, all_inclusive, direct_flight, departure_airport, url, source_trip_id, operator)
        VALUES (:source, :destination, :deal_type, :hotel_name, :hotel_stars,
            :departure_date, :return_date, :nights, :price_per_person, :price_total,
            :original_price, :savings_pct,
            :currency, :all_inclusive, :direct_flight, :departure_airport, :url, :source_trip_id, :operator)
        ON CONFLICT(source, source_trip_id) DO UPDATE SET
            price_per_person=excluded.price_per_person,
            price_total=excluded.price_total,
            original_price=excluded.original_price,
            savings_pct=excluded.savings_pct,
            deal_type=excluded.deal_type,
            operator=excluded.operator,
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
    deal_type: str = None,
    nights: list[int] = None,
    operator: str = None,
    sort_by: str = "price_per_person",
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
    if deal_type:
        query += " AND deal_type = ?"
        params.append(deal_type)
    if nights:
        placeholders = ",".join("?" for _ in nights)
        query += f" AND nights IN ({placeholders})"
        params.extend(nights)
    if operator:
        query += " AND operator = ?"
        params.append(operator)

    order = {
        "price": "price_per_person ASC",
        "deal_score": "savings_pct DESC, price_per_person ASC",
        "savings": "savings_pct DESC",
        "stars": "hotel_stars DESC, price_per_person ASC",
    }
    query += f" ORDER BY {order.get(sort_by, 'price_per_person ASC')}"

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


async def get_deal_count_by_type() -> dict:
    db = await get_db()
    cursor = await db.execute(
        "SELECT deal_type, COUNT(*) as cnt FROM deals GROUP BY deal_type"
    )
    rows = await cursor.fetchall()
    await db.close()
    return {row["deal_type"]: row["cnt"] for row in rows}


async def get_last_refresh() -> str | None:
    db = await get_db()
    cursor = await db.execute("SELECT MAX(fetched_at) FROM deals")
    row = await cursor.fetchone()
    await db.close()
    return row[0] if row else None


async def get_operators() -> list[str]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT DISTINCT operator FROM deals WHERE operator != '' ORDER BY operator"
    )
    rows = await cursor.fetchall()
    await db.close()
    return [row["operator"] for row in rows]


async def find_outliers(min_datapoints: int = 2, threshold_pct: int = 15) -> list[dict]:
    """Find deals where the price is significantly lower than the average for the same hotel+destination+deal_type.
    Only considers deals with a known departure_date so the date comparison is meaningful."""
    db = await get_db()
    cursor = await db.execute("""
        SELECT d.*,
            grp.avg_price,
            grp.datapoints,
            ROUND((grp.avg_price - d.price_per_person) / grp.avg_price * 100) AS below_avg_pct
        FROM deals d
        JOIN (
            SELECT hotel_name, destination, deal_type, nights,
                AVG(price_per_person) AS avg_price,
                COUNT(*) AS datapoints
            FROM deals
            WHERE hotel_name != '' AND price_per_person > 0 AND departure_date != ''
            GROUP BY hotel_name, destination, deal_type, nights
            HAVING COUNT(*) >= ?
        ) grp ON d.hotel_name = grp.hotel_name
            AND d.destination = grp.destination
            AND d.deal_type = grp.deal_type
            AND d.nights = grp.nights
        WHERE d.departure_date != ''
          AND (grp.avg_price - d.price_per_person) / grp.avg_price * 100 >= ?
        ORDER BY below_avg_pct DESC
    """, (min_datapoints, threshold_pct))
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in rows]
