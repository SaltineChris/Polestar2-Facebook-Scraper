"""
scraper.py — High-Performance Concurrent Scraper for Polestar 2 Listings
Scrapes Facebook Marketplace (North & South Island) and TradeMe Motors concurrently
using async Playwright with network resource blocking and SQLite persistence.
"""
import os
import sys
import json
import re
import datetime
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

import db

# Reconfigure stdout to use UTF-8 (prevents encoding crashes on Windows terminals)
if hasattr(sys.stdout, 'reconfigure') and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Paths
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("DATA_DIR", WORKSPACE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
DATA_JSON_PATH = os.path.join(DATA_DIR, "listings.json")
DATA_JS_PATH = os.path.join(DATA_DIR, "listings.js")
RUN_META_PATH = os.path.join(DATA_DIR, "run_meta.json")

# Precompiled regex patterns for speed
CLEAN_CHARS_RE = re.compile(r'[\ufffc\ufffd\x00-\x08\x0b-\x0c\x0e-\x1f]')
PRICE_DIGITS_RE = re.compile(r'\D')
FB_ITEM_RE = re.compile(r'/marketplace/item/(\d+)')
TM_ITEM_RE = re.compile(r'/listing/(\d+)|/(\d+)\.htm|(\d+)$')

SEARCH_TARGETS = [
    {
        "name": "Facebook Marketplace - North Island (Auckland + 500km)",
        "url": "https://www.facebook.com/marketplace/auckland/search/?query=polestar%202&exact=false&radius=500",
        "source": "facebook"
    },
    {
        "name": "Facebook Marketplace - South Island (Christchurch + 500km)",
        "url": "https://www.facebook.com/marketplace/christchurch/search/?query=polestar%202&exact=false&radius=500",
        "source": "facebook"
    },
    {
        "name": "TradeMe Motors - National (New Zealand)",
        "url": "https://www.trademe.co.nz/a/motors/cars/polestar/2",
        "source": "trademe"
    }
]


def clean_text(text: str) -> str:
    """Strip invalid control characters and trim whitespace."""
    if not text:
        return ""
    return CLEAN_CHARS_RE.sub('', text).strip()


def parse_price_number(price_str: str) -> int:
    """Extract digits to integer."""
    if not price_str:
        return 0
    digits = PRICE_DIGITS_RE.sub('', price_str)
    return int(digits) if digits else 0


async def block_unnecessary_resources(route):
    """Abort image, media, and font downloads to cut network latency and memory."""
    if route.request.resource_type in ["image", "media", "font"]:
        await route.abort()
    else:
        await route.continue_()


async def scrape_single_target(context, target: dict) -> list:
    """Scrape a single search target asynchronously."""
    source = target["source"]
    name = target["name"]
    url = target["url"]
    print(f"[{source.upper()}] Starting scrape for: {name}")

    page = await context.new_page()
    listings = []

    try:
        # Route interception: abort heavy media/fonts
        await page.route("**/*", block_unnecessary_resources)

        print(f"[{source.upper()}] Navigating to: {url}")
        wait_until = "domcontentloaded"
        await page.goto(url, wait_until=wait_until, timeout=50000)

        # Dynamic wait for content
        if source == "facebook":
            try:
                await page.wait_for_selector('a[href*="/marketplace/item/"]', timeout=8000)
            except Exception:
                pass
        else:
            try:
                await page.wait_for_selector('a[href*="/listing/"], a[href*="/a/motors/cars/"]', timeout=8000)
            except Exception:
                pass

        # Scroll to load dynamic items
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        await asyncio.sleep(2.0)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2.0)

        html_content = await page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        if source == "facebook":
            links = soup.find_all("a", href=FB_ITEM_RE)
            print(f"[{source.upper()}] Found {len(links)} raw marketplace links.")

            for link in links:
                href = link.get("href", "")
                if href.startswith("/"):
                    href = "https://www.facebook.com" + href
                url_clean = href.split("?")[0]

                match = FB_ITEM_RE.search(url_clean)
                if not match:
                    continue
                item_id = match.group(1)
                uniq_id = f"fb_{item_id}"

                text_content = link.get_text(separator="\n")
                lines = [clean_text(line) for line in text_content.split("\n") if clean_text(line)]

                img = link.find("img")
                img_url = img.get("src") if img else ""

                price = "N/A"
                title = "Unknown Polestar 2"
                location = "Unknown"

                if len(lines) >= 1:
                    price = lines[0]
                if len(lines) >= 2:
                    title = lines[1]
                if len(lines) >= 3:
                    location = lines[2]

                if "polestar" not in title.lower():
                    continue

                # Filter: Price must be >= $20,000 to weed out accessories/parts
                price_num = parse_price_number(price)
                if price_num < 20000:
                    continue

                listings.append({
                    "id": uniq_id,
                    "raw_id": item_id,
                    "title": title,
                    "price": price,
                    "price_num": price_num,
                    "location": location,
                    "url": url_clean,
                    "image": img_url,
                    "source": "facebook",
                    "scraped_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })

        elif source == "trademe":
            all_links = soup.find_all("a", href=True)
            listing_links = [
                l for l in all_links
                if "/listing/" in l['href'] or "/a/motors/cars/" in l['href']
            ]
            print(f"[{source.upper()}] Found {len(listing_links)} potential TradeMe listing links.")

            for link in listing_links:
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = "https://www.trademe.co.nz" + href
                url_clean = href.split("?")[0]

                match = TM_ITEM_RE.search(url_clean)
                if not match:
                    continue
                item_id = match.group(1) or match.group(2) or match.group(3)
                if not item_id:
                    continue
                uniq_id = f"tm_{item_id}"

                text_content = link.get_text(separator="\n")
                lines = [clean_text(line) for line in text_content.split("\n") if clean_text(line)]
                if len(lines) < 2:
                    continue

                img = link.find("img")
                img_url = ""
                if img:
                    img_url = img.get("src") or img.get("data-src") or img.get("srcset") or ""
                    if img_url.startswith("//"):
                        img_url = "https:" + img_url

                title = "Unknown Polestar 2"
                price = "N/A"
                location = "Unknown"

                # Find title line containing "Polestar" and "2"
                polestar_idx = -1
                for i, line in enumerate(lines):
                    if "polestar" in line.lower() and "2" in line:
                        polestar_idx = i
                        break

                if polestar_idx != -1:
                    title = lines[polestar_idx]
                    if polestar_idx + 1 < len(lines):
                        next_line = lines[polestar_idx + 1]
                        if not next_line.startswith("$") and "km" not in next_line.lower() and len(next_line) > 2:
                            title += " " + next_line

                prices = [l for l in lines if l.startswith("$") and any(c.isdigit() for c in l)]
                if prices:
                    price = prices[0]

                km_idx = -1
                for i, line in enumerate(lines):
                    if line.endswith(" km") or line.endswith(" km (approx)"):
                        km_idx = i
                        break

                if km_idx > 0:
                    location = lines[km_idx - 1]

                if "polestar" not in title.lower():
                    continue

                price_num = parse_price_number(price)
                if price_num < 20000:
                    continue

                listings.append({
                    "id": uniq_id,
                    "raw_id": item_id,
                    "title": title,
                    "price": price,
                    "price_num": price_num,
                    "location": location,
                    "url": url_clean,
                    "image": img_url,
                    "source": "trademe",
                    "scraped_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })

    except Exception as e:
        print(f"[{source.upper()}] Error scraping {name}: {e}")
    finally:
        await page.close()

    print(f"[{source.upper()}] Finished {name}: extracted {len(listings)} valid listings.")
    return listings


async def scrape_async():
    """Run all target scrapes concurrently and persist to SQLite + static files."""
    start_time = datetime.datetime.now()
    print(f"=== Starting Concurrent Polestar 2 Scraper at {start_time.isoformat()} ===")

    conn = db.init_db()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-NZ",
            timezone_id="Pacific/Auckland"
        )

        # Scrape all targets concurrently
        results = await asyncio.gather(*[
            scrape_single_target(context, target)
            for target in SEARCH_TARGETS
        ], return_exceptions=True)

        await browser.close()

    # Deduplicate and upsert into SQLite
    all_scraped = []
    seen_ids = set()
    for res in results:
        if isinstance(res, list):
            for item in res:
                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    all_scraped.append(item)

    print(f"\nTotal unique valid listings scraped: {len(all_scraped)}")

    new_additions = []
    price_drops = []
    new_by_source = {"facebook": 0, "trademe": 0}

    for item in all_scraped:
        updated = db.upsert_scraped_listing(conn, item)
        if updated.get("is_new"):
            new_additions.append(updated)
            src = updated.get("source", "facebook")
            new_by_source[src] = new_by_source.get(src, 0) + 1
            print(f"[NEW LISTING] [{src.upper()}] {updated['title']} - {updated['price']}")
        if (updated.get("price_drop") or 0) > 0:
            price_drops.append(updated)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    run_meta = {
        "last_scraped": now_utc.isoformat(),
        "new_facebook": new_by_source.get("facebook", 0),
        "new_trademe": new_by_source.get("trademe", 0),
        "price_drops": len(price_drops)
    }

    meta = db.export_to_files(conn, run_meta)
    db.record_scrape_run(conn, meta)

    elapsed = (datetime.datetime.now() - start_time).total_seconds()
    print(f"=== Scrape completed in {elapsed:.1f}s ===")
    print(f"Saved {meta['total_facebook'] + meta['total_trademe']} total active listings.")
    print(f"New: {meta['new_facebook']} Facebook, {meta['new_trademe']} TradeMe. Price drops: {len(price_drops)}.")

    # Git auto-push if configured and changes detected
    if os.getenv("GITHUB_ACTIONS") != "true" and os.getenv("SKIP_GIT_PUSH") != "1":
        import subprocess
        try:
            status = subprocess.run(["git", "status", "--porcelain", DATA_JSON_PATH, DATA_JS_PATH], capture_output=True, text=True)
            if status.stdout.strip():
                print("Detected changes in listings data. Committing and pushing to GitHub...")
                subprocess.run(["git", "add", DATA_JSON_PATH, DATA_JS_PATH], check=True)
                subprocess.run(["git", "commit", "-m", "Auto-update listings data [skip ci]"], check=True)
                subprocess.run(["git", "push"], check=True)
                print("Successfully pushed updates to GitHub.")
            else:
                print("No data changes detected. Skipping git push.")
        except Exception as e:
            print(f"Git auto-push check failed: {e}")

    return new_additions


def scrape():
    """Synchronous entry point for callers like api_server.py or bat scripts."""
    return asyncio.run(scrape_async())


if __name__ == "__main__":
    new_items = scrape()
    if new_items:
        print(f"\nNOTIFICATION: {len(new_items)} new Polestar 2 listing(s) found!")
    else:
        print("\nNo new listings found in this run.")
