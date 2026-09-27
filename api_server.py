"""
api_server.py — Polestar 2 Listings REST API
Serves cached listings data and historical price-drops to GitHub Actions and client apps.
Features SQLite persistence, HTTP ETag conditional caching (304 Not Modified),
and background scraper triggers.

Start: python api_server.py
Requires API_TOKEN env var set to a strong secret for Bearer token auth.
"""
import os
import sys
import json
import hashlib
import threading
import time
import datetime
from functools import wraps
from flask import Flask, jsonify, abort, request, make_response
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import db

# Reconfigure stdout to use UTF-8 on Windows terminals
if hasattr(sys.stdout, 'reconfigure') and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

app = Flask(__name__)

# CORS: only allow requests from the GitHub Pages dashboard
CORS(app, origins=[
    "https://polestar.sivoravong.com",
    "http://localhost",
    "http://127.0.0.1",
])

# Rate limiting: default 30 requests/minute per IP
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["30 per minute"],
    storage_uri="memory://",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)

# API_TOKEN is required — server refuses to start without it
API_TOKEN = os.getenv("API_TOKEN")
if not API_TOKEN:
    raise RuntimeError(
        "API_TOKEN environment variable is not set. "
        "Set it to a strong secret to secure the API (e.g. API_TOKEN=your-secret-here)."
    )

is_scraping = False
scrape_lock = threading.Lock()


def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {API_TOKEN}":
            abort(401)
        return f(*args, **kwargs)
    return decorated


@app.route("/listings", methods=["GET"])
@require_token
def get_listings():
    """
    Return all active listings plus run metadata as JSON.
    Supports HTTP ETag conditional caching (304 Not Modified)
    and optional filtering (?source=facebook&price_drops=true).
    """
    source = request.args.get("source")
    price_drops_only = request.args.get("price_drops", "").lower() in ["true", "1", "yes"]
    min_price = request.args.get("min_price", type=int)
    max_price = request.args.get("max_price", type=int)

    try:
        conn = db.get_db_connection()
        listings = db.get_all_listings(
            conn,
            source=source,
            price_drops_only=price_drops_only,
            min_price=min_price,
            max_price=max_price
        )
    except Exception as e:
        app.logger.error(f"Database query failed: {e}")
        return jsonify({"error": "Internal server error"}), 500

    # Load run metadata
    run_meta = {}
    meta_path = os.path.join(DATA_DIR, "run_meta.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                run_meta = json.load(f)
        except Exception:
            pass

    # Compute ETag for caching
    last_scraped_str = run_meta.get("last_scraped", "")
    tag_input = f"{last_scraped_str}:{len(listings)}:{source}:{price_drops_only}:{min_price}:{max_price}"
    etag = f'"{hashlib.sha256(tag_input.encode("utf-8")).hexdigest()[:16]}"'

    # Check client If-None-Match header
    client_etag = request.headers.get("If-None-Match")
    if client_etag and client_etag == etag:
        res = make_response("", 304)
        res.headers["ETag"] = etag
        return res

    payload = {
        "count": len(listings),
        "meta": run_meta,
        "listings": listings
    }
    response = make_response(jsonify(payload))
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=60"
    return response


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint with database stats — no auth required."""
    db_exists = os.path.exists(os.path.join(DATA_DIR, "polestar.db"))
    listings_count = 0
    if db_exists:
        try:
            conn = db.get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as cnt FROM listings WHERE is_active = 1")
            listings_count = cur.fetchone()["cnt"]
        except Exception:
            pass

    return jsonify({
        "status": "ok",
        "database_connected": db_exists,
        "active_listings": listings_count,
        "is_scraping": is_scraping
    })


def run_scrape_background():
    """Background runner for scraper execution."""
    global is_scraping
    with scrape_lock:
        if is_scraping:
            print("Scrape already in progress. Skipping.")
            return False
        is_scraping = True

    try:
        from scraper import scrape
        print("Starting Polestar 2 scrape background task...")
        scrape()
        print("Polestar 2 scrape background task finished successfully.")
    except Exception as e:
        print(f"Error during Polestar 2 scrape task: {e}")
    finally:
        with scrape_lock:
            is_scraping = False
    return True


@app.route("/scrape", methods=["POST"])
@require_token
@limiter.limit("3 per hour")
def trigger_scrape():
    """Trigger an immediate background scrape run."""
    if is_scraping:
        return jsonify({"status": "busy", "message": "Scrape already in progress"}), 409
    t = threading.Thread(target=run_scrape_background, daemon=True)
    t.start()
    return jsonify({"status": "started", "message": "Background scrape started"}), 202


def start_auto_scheduler(interval_hours):
    """Background thread that triggers scrape every interval_hours."""
    interval_seconds = interval_hours * 3600
    print(f"Polestar Auto-Scheduler active: Scrapes scheduled every {interval_hours} hours.")

    def loop():
        time.sleep(15)  # Wait 15 seconds after startup
        while True:
            should_run = False
            last_run_dt = None
            meta_file = os.path.join(DATA_DIR, "run_meta.json")

            if os.path.exists(meta_file):
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    lr_str = meta.get("last_scraped")
                    if lr_str:
                        last_run_dt = datetime.datetime.fromisoformat(lr_str)
                except Exception:
                    pass

            now = datetime.datetime.now(datetime.timezone.utc)
            if not last_run_dt or (now - last_run_dt).total_seconds() >= interval_seconds:
                should_run = True

            if should_run and not is_scraping:
                print(f"Auto-scheduler triggering scheduled scrape (interval: {interval_hours}h)...")
                run_scrape_background()

            time.sleep(60)

    t = threading.Thread(target=loop, daemon=True)
    t.start()


if __name__ == "__main__":
    db.init_db()
    port = int(os.getenv("PORT", 5000))
    auto_hours = int(os.getenv("AUTO_SCRAPE_HOURS", "12"))
    if auto_hours > 0:
        start_auto_scheduler(auto_hours)

    print(f"Starting Polestar 2 API server on port {port}...")
    print("Auth: Bearer token required (API_TOKEN)")
    app.run(host="0.0.0.0", port=port, debug=False)
