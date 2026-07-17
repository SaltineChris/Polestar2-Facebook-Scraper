"""
api_server.py — Polestar 2 Listings REST API
Runs on the Raspberry Pi and serves listings data to GitHub Actions.

Start: python api_server.py
Set environment variable API_TOKEN to a secret string to enable Bearer token auth.
"""
import os
import json
from flask import Flask, jsonify, abort, request
from functools import wraps

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LISTINGS_JSON = os.path.join(BASE_DIR, "listings.json")
RUN_META_JSON = os.path.join(BASE_DIR, "run_meta.json")

# Set API_TOKEN env var to require Bearer token auth (recommended)
API_TOKEN = os.getenv("API_TOKEN")

def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if API_TOKEN:
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {API_TOKEN}":
                abort(401)
        return f(*args, **kwargs)
    return decorated


@app.route("/listings", methods=["GET"])
@require_token
def get_listings():
    """Return all listings plus run metadata as JSON."""
    try:
        with open(LISTINGS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        listings = list(data.values())
    except FileNotFoundError:
        return jsonify({"error": "No listings data yet. Run scraper.py first."}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Load run metadata if available
    run_meta = {}
    try:
        with open(RUN_META_JSON, "r", encoding="utf-8") as f:
            run_meta = json.load(f)
    except FileNotFoundError:
        pass

    return jsonify({
        "count": len(listings),
        "meta": run_meta,
        "listings": listings
    })


@app.route("/health", methods=["GET"])
def health():
    """Simple health check endpoint — no auth required."""
    listings_exists = os.path.exists(LISTINGS_JSON)
    meta_exists = os.path.exists(RUN_META_JSON)
    return jsonify({
        "status": "ok",
        "listings_available": listings_exists,
        "meta_available": meta_exists,
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"Starting Polestar 2 API server on port {port}...")
    print(f"Auth: {'Token required' if API_TOKEN else 'No auth (set API_TOKEN env var to enable)'}")
    app.run(host="0.0.0.0", port=port, debug=False)
