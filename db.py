"""
db.py — SQLite Persistence & Price-Drop Tracking Engine for Polestar 2 Scraper
Provides high-concurrency WAL-mode SQLite storage, historical price tracking,
migration from legacy JSON files, and static file export for GitHub Pages.
"""
import os
import sys
import sqlite3
import json
import re
import datetime

# Reconfigure stdout to use UTF-8 on Windows terminals
if hasattr(sys.stdout, 'reconfigure') and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_DB_PATH = os.path.join(DATA_DIR, "polestar.db")
DATA_JSON_PATH = os.path.join(DATA_DIR, "listings.json")
DATA_JS_PATH = os.path.join(DATA_DIR, "listings.js")
RUN_META_PATH = os.path.join(DATA_DIR, "run_meta.json")

PRICE_DIGITS_RE = re.compile(r'\D')


def parse_price_number(price_str: str) -> int:
    """Extract numeric integer price from price string (e.g. 'NZ$52,900' -> 52900)."""
    if not price_str:
        return 0
    digits = PRICE_DIGITS_RE.sub('', price_str)
    return int(digits) if digits else 0


def get_db_connection(db_path: str = None) -> sqlite3.Connection:
    """Connect to SQLite with WAL mode, foreign keys, and Row factory."""
    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str = None) -> sqlite3.Connection:
    """Initialize database tables and run migration if empty."""
    conn = get_db_connection(db_path)
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS listings (
                id TEXT PRIMARY KEY,
                raw_id TEXT,
                title TEXT NOT NULL,
                price TEXT NOT NULL,
                price_num INTEGER NOT NULL,
                previous_price TEXT,
                previous_price_num INTEGER,
                price_drop INTEGER DEFAULT 0,
                location TEXT,
                url TEXT,
                image TEXT,
                source TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                scraped_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                is_new INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_listings_source ON listings(source);
            CREATE INDEX IF NOT EXISTS idx_listings_scraped_at ON listings(scraped_at);
            CREATE INDEX IF NOT EXISTS idx_listings_price_drop ON listings(price_drop);
            CREATE INDEX IF NOT EXISTS idx_listings_active ON listings(is_active);

            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id TEXT NOT NULL,
                price TEXT NOT NULL,
                price_num INTEGER NOT NULL,
                recorded_at TEXT NOT NULL,
                FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_price_history_listing ON price_history(listing_id);

            CREATE TABLE IF NOT EXISTS scrape_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TEXT NOT NULL,
                new_facebook INTEGER DEFAULT 0,
                new_trademe INTEGER DEFAULT 0,
                total_facebook INTEGER DEFAULT 0,
                total_trademe INTEGER DEFAULT 0,
                price_drops INTEGER DEFAULT 0
            );
        """)

    # Migrate from existing listings.json if DB has 0 listings
    migrate_from_json_if_empty(conn)
    return conn


def migrate_from_json_if_empty(conn: sqlite3.Connection, json_path: str = None) -> int:
    """Migrate existing listings.json into SQLite if table is empty."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM listings")
    count = cur.fetchone()["cnt"]
    if count > 0:
        return 0  # Already initialized

    path = json_path or DATA_JSON_PATH
    if not os.path.exists(path) and os.path.exists(os.path.join(BASE_DIR, "listings.json")):
        path = os.path.join(BASE_DIR, "listings.json")

    if not os.path.exists(path):
        return 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Notice: Could not load {path} for migration: {e}")
        return 0

    imported = 0
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with conn:
        for item_id, item in data.items():
            price_str = item.get("price", "N/A")
            price_num = parse_price_number(price_str)
            scraped_at = item.get("scraped_at") or now_iso
            source = item.get("source", "facebook")
            
            clean_id = item.get("id", item_id)
            if not clean_id.startswith("fb_") and not clean_id.startswith("tm_"):
                clean_id = f"fb_{clean_id}" if source == "facebook" else f"tm_{clean_id}"

            conn.execute("""
                INSERT OR IGNORE INTO listings (
                    id, raw_id, title, price, price_num,
                    previous_price, previous_price_num, price_drop,
                    location, url, image, source,
                    first_seen, last_seen, scraped_at,
                    is_active, is_new
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0)
            """, (
                clean_id,
                item.get("raw_id", ""),
                item.get("title", "Polestar 2"),
                price_str,
                price_num,
                None,
                None,
                0,
                item.get("location", "Unknown"),
                item.get("url", ""),
                item.get("image", ""),
                source,
                scraped_at,
                scraped_at,
                scraped_at
            ))

            if price_num > 0:
                conn.execute("""
                    INSERT INTO price_history (listing_id, price, price_num, recorded_at)
                    VALUES (?, ?, ?, ?)
                """, (clean_id, price_str, price_num, scraped_at))

            imported += 1

    print(f"Successfully migrated {imported} listings from JSON to SQLite.")
    return imported


def upsert_scraped_listing(conn: sqlite3.Connection, item: dict) -> dict:
    """
    Insert or update a scraped listing.
    Detects price drops and logs price history snapshots.
    Returns the updated listing dict with price_drop and is_new flags.
    """
    item_id = item["id"]
    current_price_str = item.get("price", "N/A")
    current_price_num = parse_price_number(current_price_str)
    now_iso = item.get("scraped_at") or datetime.datetime.now(datetime.timezone.utc).isoformat()

    cur = conn.cursor()
    cur.execute("SELECT * FROM listings WHERE id = ?", (item_id,))
    existing = cur.fetchone()

    is_new = False
    price_drop = 0
    prev_price_str = None
    prev_price_num = None

    if existing is None:
        # Brand new listing
        is_new = True
        with conn:
            conn.execute("""
                INSERT INTO listings (
                    id, raw_id, title, price, price_num,
                    previous_price, previous_price_num, price_drop,
                    location, url, image, source,
                    first_seen, last_seen, scraped_at,
                    is_active, is_new
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
            """, (
                item_id,
                item.get("raw_id", ""),
                item.get("title", ""),
                current_price_str,
                current_price_num,
                None,
                None,
                0,
                item.get("location", "Unknown"),
                item.get("url", ""),
                item.get("image", ""),
                item.get("source", "facebook"),
                now_iso,
                now_iso,
                now_iso
            ))
            if current_price_num > 0:
                conn.execute("""
                    INSERT INTO price_history (listing_id, price, price_num, recorded_at)
                    VALUES (?, ?, ?, ?)
                """, (item_id, current_price_str, current_price_num, now_iso))

    else:
        # Existing listing: compare price
        existing_price_num = existing["price_num"]
        existing_price_str = existing["price"]
        prev_price_str = existing["previous_price"]
        prev_price_num = existing["previous_price_num"]
        price_drop = existing["price_drop"] or 0

        # Check if price changed
        if current_price_num > 0 and existing_price_num > 0 and current_price_num != existing_price_num:
            if current_price_num < existing_price_num:
                # Price dropped!
                diff = existing_price_num - current_price_num
                price_drop = diff
                prev_price_str = existing_price_str
                prev_price_num = existing_price_num
                print(f"[PRICE DROP] {item['title']}: {existing_price_str} -> {current_price_str} (-${diff:,})")
            else:
                # Price increased
                price_drop = 0
                prev_price_str = existing_price_str
                prev_price_num = existing_price_num

            # Log snapshot to price_history
            conn.execute("""
                INSERT INTO price_history (listing_id, price, price_num, recorded_at)
                VALUES (?, ?, ?, ?)
            """, (item_id, current_price_str, current_price_num, now_iso))

        # Update listing details
        with conn:
            conn.execute("""
                UPDATE listings SET
                    title = ?,
                    price = ?,
                    price_num = ?,
                    previous_price = ?,
                    previous_price_num = ?,
                    price_drop = ?,
                    location = ?,
                    url = ?,
                    image = ?,
                    source = ?,
                    last_seen = ?,
                    is_active = 1,
                    is_new = 0
                WHERE id = ?
            """, (
                item.get("title", existing["title"]),
                current_price_str,
                current_price_num,
                prev_price_str,
                prev_price_num,
                price_drop,
                item.get("location", existing["location"]),
                item.get("url", existing["url"]),
                item.get("image") or existing["image"],
                item.get("source", existing["source"]),
                now_iso,
                item_id
            ))

    res = dict(item)
    res["is_new"] = is_new
    res["price_drop"] = price_drop
    res["previous_price"] = prev_price_str
    res["previous_price_num"] = prev_price_num
    res["scraped_at"] = existing["scraped_at"] if existing else now_iso
    return res


def get_all_listings(conn: sqlite3.Connection, source: str = None, price_drops_only: bool = False, min_price: int = None, max_price: int = None) -> list:
    """Retrieve all active listings with optional filtering."""
    query = "SELECT * FROM listings WHERE is_active = 1"
    params = []

    if source and source != "all":
        query += " AND source = ?"
        params.append(source)
    if price_drops_only:
        query += " AND price_drop > 0"
    if min_price is not None:
        query += " AND price_num >= ?"
        params.append(min_price)
    if max_price is not None:
        query += " AND price_num <= ?"
        params.append(max_price)

    query += " ORDER BY scraped_at DESC"

    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()

    listings = []
    for r in rows:
        listings.append({
            "id": r["id"],
            "raw_id": r["raw_id"],
            "title": r["title"],
            "price": r["price"],
            "price_num": r["price_num"],
            "previous_price": r["previous_price"],
            "previous_price_num": r["previous_price_num"],
            "price_drop": r["price_drop"],
            "location": r["location"],
            "url": r["url"],
            "image": r["image"],
            "source": r["source"],
            "first_seen": r["first_seen"],
            "last_seen": r["last_seen"],
            "scraped_at": r["scraped_at"],
            "is_new": bool(r["is_new"])
        })
    return listings


def record_scrape_run(conn: sqlite3.Connection, meta: dict):
    """Insert a scrape run record into scrape_runs table."""
    with conn:
        conn.execute("""
            INSERT INTO scrape_runs (
                run_at, new_facebook, new_trademe,
                total_facebook, total_trademe, price_drops
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            meta.get("last_scraped"),
            meta.get("new_facebook", 0),
            meta.get("new_trademe", 0),
            meta.get("total_facebook", 0),
            meta.get("total_trademe", 0),
            meta.get("price_drops", 0)
        ))


def export_to_files(conn: sqlite3.Connection, run_meta: dict = None) -> dict:
    """
    Export database records to listings.json, listings.js, and run_meta.json
    for static GitHub Pages hosting and backwards compatibility.
    """
    listings = get_all_listings(conn)
    keyed = {item["id"]: item for item in listings}

    fb_count = sum(1 for item in listings if item["source"] == "facebook")
    tm_count = sum(1 for item in listings if item["source"] == "trademe")
    drops_count = sum(1 for item in listings if (item.get("price_drop") or 0) > 0)

    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    meta = {
        "last_scraped": run_meta.get("last_scraped", now_utc) if run_meta else now_utc,
        "new_facebook": run_meta.get("new_facebook", 0) if run_meta else 0,
        "new_trademe": run_meta.get("new_trademe", 0) if run_meta else 0,
        "total_facebook": fb_count,
        "total_trademe": tm_count,
        "price_drops": drops_count
    }

    # 1. Save listings.json
    with open(DATA_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(keyed, f, indent=2, ensure_ascii=False)

    # 2. Save run_meta.json
    with open(RUN_META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    # 3. Save listings.js (for client-side browser loading)
    js_content = f"window.marketplaceListings = {json.dumps(listings, indent=2, ensure_ascii=False)};\n"
    js_content += f"window.lastRunMeta = {json.dumps(meta, indent=2, ensure_ascii=False)};"
    with open(DATA_JS_PATH, "w", encoding="utf-8") as f:
        f.write(js_content)

    return meta


if __name__ == "__main__":
    conn = init_db()
    meta = export_to_files(conn)
    print(f"Database initialization and export complete. Total listings: {len(get_all_listings(conn))}")
