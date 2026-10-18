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
import hmac
import hashlib
import threading
import time
import datetime
from contextlib import closing
from functools import wraps
from flask import Flask, jsonify, abort, request, make_response, send_from_directory
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)

# Disable automatic root static_folder to prevent exposing .db and .py files (SEC-01)
app = Flask(__name__, static_folder=None)

ALLOWED_STATIC_FILES = {"index.html", "style.css", "app.js", "listings.js"}

# CORS: allow dashboard requests from GitHub Pages and local development (SEC-06)
DEFAULT_CORS_ORIGINS = [
    "https://polestar.sivoravong.com",
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "http://localhost:25000",
    "http://127.0.0.1:25000",
]
cors_env = os.getenv("CORS_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in cors_env.split(",") if o.strip()] if cors_env else DEFAULT_CORS_ORIGINS
CORS(app, origins=ALLOWED_ORIGINS)


def get_client_ip():
    """Resolve client IP, optionally trusting Cloudflare / reverse proxy headers when TRUST_PROXY=1."""
    if os.getenv("TRUST_PROXY") == "1":
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip.strip()
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
    return get_remote_address()


# Rate limiting: default 30 requests/minute per IP
limiter = Limiter(
    get_client_ip,
    app=app,
    default_limits=["30 per minute"],
    storage_uri="memory://",
)

# API_TOKEN for securing administrative endpoints (fail-closed unless ALLOW_UNAUTHENTICATED_DEV=1)
API_TOKEN = os.getenv("API_TOKEN", "")
ALLOW_UNAUTHENTICATED_DEV = os.getenv("ALLOW_UNAUTHENTICATED_DEV", "") == "1"

is_scraping = False
last_scrape_attempt_ts = 0.0
scrape_lock = threading.Lock()
SCRAPE_COOLDOWN_SECONDS = 3600  # 1-hour minimum window between scrapes


@app.after_request
def set_security_headers(response):
    """Attach defensive HTTP security headers to all responses."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' https: data:; "
        "connect-src 'self' http://localhost:5000 http://127.0.0.1:5000; "
        "frame-ancestors 'none'; "
        "base-uri 'self';"
    )
    return response


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        "status": "rate_limited",
        "error": "Rate limit exceeded",
        "message": "Scraper can only be run once per hour. Please wait before triggering another update."
    }), 429


@app.route("/", methods=["GET"])
def index():
    """Serve the tracker dashboard."""
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/<path:filename>", methods=["GET"])
def serve_static(filename):
    """Serve only explicitly allowlisted static frontend assets."""
    if filename not in ALLOWED_STATIC_FILES:
        abort(404)
    if filename == "listings.js" and os.path.exists(os.path.join(DATA_DIR, "listings.js")):
        return send_from_directory(DATA_DIR, "listings.js")
    return send_from_directory(BASE_DIR, filename)


def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not API_TOKEN:
            if ALLOW_UNAUTHENTICATED_DEV:
                return f(*args, **kwargs)
            return jsonify({"error": "Server authentication not configured (API_TOKEN missing)"}), 503
        auth = request.headers.get("Authorization", "")
        expected = f"Bearer {API_TOKEN}"
        if not hmac.compare_digest(auth.encode("utf-8"), expected.encode("utf-8")):
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
        with closing(db.get_db_connection()) as conn:
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
    response.headers["Cache-Control"] = "private, max-age=60"
    return response


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint with database stats — no auth required."""
    db_exists = os.path.exists(os.path.join(DATA_DIR, "polestar.db"))
    listings_count = 0
    if db_exists:
        try:
            with closing(db.get_db_connection()) as conn:
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


def run_scrape_background(already_locked=False):
    """Background runner for scraper execution."""
    global is_scraping, last_scrape_attempt_ts
    if not already_locked:
        with scrape_lock:
            if is_scraping:
                print("Scrape already in progress. Skipping.")
                return False
            is_scraping = True
            last_scrape_attempt_ts = time.time()

    try:
        from scraper import scrape
        print("Starting Polestar 2 scrape background task...")
        scrape(git_push=False)
        print("Polestar 2 scrape background task finished successfully.")
    except Exception as e:
        print(f"Error during Polestar 2 scrape task: {e}")
    finally:
        with scrape_lock:
            is_scraping = False
    return True


def get_seconds_since_last_scrape():
    """Return seconds elapsed since the last completed or attempted scrape."""
    elapsed_candidates = []
    if last_scrape_attempt_ts > 0:
        elapsed_candidates.append(max(0.0, time.time() - last_scrape_attempt_ts))

    meta_path = os.path.join(DATA_DIR, "run_meta.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            ls = meta.get("last_scraped")
            if ls:
                dt = datetime.datetime.fromisoformat(ls)
                now = datetime.datetime.now(datetime.timezone.utc)
                elapsed_candidates.append(max(0.0, (now - dt).total_seconds()))
        except Exception:
            pass
    return min(elapsed_candidates) if elapsed_candidates else None


@app.route("/scrape", methods=["POST"])
@limiter.limit("1 per hour")
def trigger_scrape():
    """
    Trigger an immediate background scrape run.
    Rate limited to once per hour, enforced server-side.
    No credentials required.
    """
    global is_scraping, last_scrape_attempt_ts
    with scrape_lock:
        if is_scraping:
            return jsonify({"status": "busy", "message": "A scrape is already in progress on the server."}), 409

        # Enforce 1-hour rate limit based on last scrape timestamp
        elapsed = get_seconds_since_last_scrape()
        if elapsed is not None and elapsed < SCRAPE_COOLDOWN_SECONDS:
            remaining_mins = max(1, int((SCRAPE_COOLDOWN_SECONDS - elapsed) / 60))
            return jsonify({
                "status": "rate_limited",
                "message": f"Scraper can only run once every hour. Cooldown active for {remaining_mins} more minute(s)."
            }), 429

        is_scraping = True
        last_scrape_attempt_ts = time.time()

    t = threading.Thread(target=run_scrape_background, kwargs={"already_locked": True}, daemon=True)
    t.start()
    return jsonify({
        "status": "started",
        "message": "Background scrape started successfully across TradeMe and Facebook Marketplace."
    }), 202


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
    with closing(db.init_db()):
        pass
    port = int(os.getenv("PORT", 5000))
    auto_hours = int(os.getenv("AUTO_SCRAPE_HOURS", "12"))
    if auto_hours > 0:
        start_auto_scheduler(auto_hours)

    print(f"Starting Polestar 2 API server on port {port}...")
    if API_TOKEN:
        print("Auth: Bearer token active for secured endpoints (API_TOKEN set)")
    elif ALLOW_UNAUTHENTICATED_DEV:
        print("Auth: Open local dev mode (ALLOW_UNAUTHENTICATED_DEV=1)")
    else:
        print("WARNING: API_TOKEN is not set. Protected endpoints will return 503 until API_TOKEN or ALLOW_UNAUTHENTICATED_DEV=1 is set.")
    print("Scraper endpoint: POST /scrape (enforced 1/hour rate limit, no credentials required)")
    app.run(host="0.0.0.0", port=port, debug=False)
