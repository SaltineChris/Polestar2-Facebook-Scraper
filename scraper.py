import os
import sys
import json
import re
import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# Reconfigure stdout to use UTF-8 (prevents encoding crashes on Windows terminals)
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Define paths
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_JSON_PATH = os.path.join(WORKSPACE_DIR, "listings.json")
DATA_JS_PATH = os.path.join(WORKSPACE_DIR, "listings.js")

def parse_price_number(price_str):
    # Extract digits
    digits = re.sub(r'\D', '', price_str)
    if not digits:
        return 0
    return int(digits)

def load_existing_listings():
    if os.path.exists(DATA_JSON_PATH):
        try:
            with open(DATA_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Migration: ensure all existing records have a source and clean ID prefix
                migrated = {}
                for item_id, item in data.items():
                    if "source" not in item:
                        item["source"] = "facebook"
                    # Ensure ID format uses prefix (fb_ or tm_) to prevent clashes
                    new_id = item["id"]
                    if not new_id.startswith("fb_") and not new_id.startswith("tm_"):
                        if item["source"] == "facebook":
                            new_id = f"fb_{new_id}"
                        else:
                            new_id = f"tm_{new_id}"
                    item["id"] = new_id
                    migrated[new_id] = item
                return migrated
        except Exception as e:
            print(f"Error loading listings.json: {e}")
    return {}

def save_listings(listings):
    # Save to JSON
    with open(DATA_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(listings, f, indent=2, ensure_ascii=False)
    
    # Save to JS for local HTML client-side loading
    js_content = f"window.marketplaceListings = {json.dumps(list(listings.values()), indent=2, ensure_ascii=False)};\n"
    js_content += f"window.lastChecked = '{datetime.datetime.now().isoformat()}';"
    with open(DATA_JS_PATH, "w", encoding="utf-8") as f:
        f.write(js_content)

def scrape():
    print(f"Starting Polestar 2 scraper at {datetime.datetime.now().isoformat()}...")
    existing = load_existing_listings()
    new_additions = []
    current_listings = {}

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

    with sync_playwright() as p:
        # Launch browser with human-like configurations
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        
        # Create context with standard user agent and viewport
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-NZ",
            timezone_id="Pacific/Auckland"
        )
        
        for target in SEARCH_TARGETS:
            print(f"\nScraping location target: {target['name']}")
            page = context.new_page()
            
            # Go to search URL
            print(f"Navigating to: {target['url']}")
            try:
                # TradeMe is heavy, load with domcontentloaded
                wait_until = "domcontentloaded" if target["source"] == "trademe" else "networkidle"
                page.goto(target['url'], wait_until=wait_until, timeout=45000)
                
                # Wait for content hydration
                page.wait_for_timeout(10000 if target["source"] == "trademe" else 5000)
                
                # Scroll down to load more results
                print("Scrolling page to load more listings...")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                page.wait_for_timeout(3000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(3000)

                # Grab page HTML content
                html_content = page.content()
                soup = BeautifulSoup(html_content, "html.parser")
                
                if target["source"] == "facebook":
                    # Facebook parsing logic
                    links = soup.find_all("a", href=re.compile(r"/marketplace/item/\d+"))
                    print(f"Found {len(links)} raw Facebook marketplace links.")

                    for link in links:
                        href = link.get("href")
                        if href.startswith("/"):
                            href = "https://www.facebook.com" + href
                        url_clean = href.split("?")[0]
                        
                        match = re.search(r"/marketplace/item/(\d+)", url_clean)
                        if not match:
                            continue
                        item_id = match.group(1)
                        uniq_id = f"fb_{item_id}"
                        
                        if uniq_id in current_listings:
                            continue
                            
                        text_content = link.get_text(separator="\n")
                        lines = [line.strip() for line in text_content.split("\n") if line.strip()]
                        
                        img = link.find("img")
                        img_url = img.get("src") if img else ""

                        price = "N/A"
                        title = "Unknown Polestar 2"
                        location = "Unknown"
                        
                        if len(lines) >= 1:
                            price = re.sub(r'[\ufffc\ufffd\x00-\x08\x0b-\x0c\x0e-\x1f]', '', lines[0])
                        if len(lines) >= 2:
                            title = re.sub(r'[\ufffc\ufffd\x00-\x08\x0b-\x0c\x0e-\x1f]', '', lines[1])
                        if len(lines) >= 3:
                            location = re.sub(r'[\ufffc\ufffd\x00-\x08\x0b-\x0c\x0e-\x1f]', '', lines[2])
                            
                        if "polestar" not in title.lower():
                            continue

                        # Filter: Price must be >= $20,000 to weed out accessories/parts
                        price_num = parse_price_number(price)
                        if price_num < 20000:
                            print(f"Skipping Facebook listing under $20k: {title} ({price})")
                            continue

                        current_listings[uniq_id] = {
                            "id": uniq_id,
                            "raw_id": item_id,
                            "title": title,
                            "price": price,
                            "location": location,
                            "url": url_clean,
                            "image": img_url,
                            "source": "facebook",
                            "scraped_at": datetime.datetime.now().isoformat(),
                            "is_new": False
                        }
                        
                elif target["source"] == "trademe":
                    # TradeMe parsing logic
                    links = soup.find_all("a", href=True)
                    listing_links = []
                    for l in links:
                        href = l['href']
                        if "/listing/" in href or "/a/motors/cars/" in href:
                            listing_links.append(l)
                            
                    print(f"Found {len(listing_links)} potential TradeMe listing links.")
                    
                    for link in listing_links:
                        href = link.get("href")
                        if not href.startswith("http"):
                            href = "https://www.trademe.co.nz" + href
                        url_clean = href.split("?")[0]
                        
                        match = re.search(r"/listing/(\d+)|/(\d+)\.htm", url_clean)
                        if not match:
                            match = re.search(r"(\d+)$", url_clean)
                            
                        if not match:
                            continue
                        item_id = match.group(1) or match.group(2)
                        uniq_id = f"tm_{item_id}"
                        
                        if uniq_id in current_listings:
                            continue
                            
                        text_content = link.get_text(separator="\n")
                        lines = [line.strip() for line in text_content.split("\n") if line.strip()]
                        
                        if len(lines) < 2:
                            continue
                            
                        img = link.find("img")
                        img_url = ""
                        if img:
                            img_url = img.get("src") or img.get("data-src") or img.get("srcset") or ""
                            if img_url.startswith("//"):
                                img_url = "https:" + img_url
                        
                        # Use TradeMe parsing heuristics
                        title = "Unknown Polestar 2"
                        price = "N/A"
                        location = "Unknown"
                        
                        # Find title line containing "Polestar 2" (usually has year)
                        polestar_idx = -1
                        for i, line in enumerate(lines):
                            if "polestar" in line.lower() and "2" in line:
                                polestar_idx = i
                                break
                        
                        if polestar_idx != -1:
                            title = re.sub(r'[\ufffc\ufffd\x00-\x08\x0b-\x0c\x0e-\x1f]', '', lines[polestar_idx])
                            # Append the next line if it adds submodel context
                            if polestar_idx + 1 < len(lines):
                                next_line = lines[polestar_idx + 1]
                                if not next_line.startswith("$") and "km" not in next_line.lower() and len(next_line) > 2:
                                    title += " " + re.sub(r'[\ufffc\ufffd\x00-\x08\x0b-\x0c\x0e-\x1f]', '', next_line)
                        
                        # Find price starting with "$"
                        prices = [l for l in lines if l.startswith("$") and any(c.isdigit() for c in l)]
                        if prices:
                            price = re.sub(r'[\ufffc\ufffd\x00-\x08\x0b-\x0c\x0e-\x1f]', '', prices[0])
                            
                        # Find location: search for line ending in " km" and get preceding
                        km_idx = -1
                        for i, line in enumerate(lines):
                            if line.endswith(" km") or line.endswith(" km (approx)"):
                                km_idx = i
                                break
                        
                        if km_idx > 0:
                            location = re.sub(r'[\ufffc\ufffd\x00-\x08\x0b-\x0c\x0e-\x1f]', '', lines[km_idx - 1])
                        
                        # Clean up name/brand filters
                        if "polestar" not in title.lower():
                            continue
                            
                        # Filter: Price must be >= $20,000
                        price_num = parse_price_number(price)
                        if price_num < 20000:
                            print(f"Skipping TradeMe listing under $20k: {title} ({price})")
                            continue
                            
                        current_listings[uniq_id] = {
                            "id": uniq_id,
                            "raw_id": item_id,
                            "title": title,
                            "price": price,
                            "location": location,
                            "url": url_clean,
                            "image": img_url,
                            "source": "trademe",
                            "scraped_at": datetime.datetime.now().isoformat(),
                            "is_new": False
                        }
                        
            except Exception as e:
                print(f"Error scraping {target['name']}: {e}")
            finally:
                page.close()

        browser.close()

    # Compare with existing listings
    print(f"\nScraped {len(current_listings)} valid listings across all targets.")
    
    # Update listings. Set "is_new" to True for new listings
    updated_listings = {}
    for item_id, data in current_listings.items():
        if item_id not in existing:
            data["is_new"] = True
            new_additions.append(data)
            print(f"NEW LISTING FOUND [{data['source'].upper()}]: {data['title']} - {data['price']}")
        else:
            # Preserve scraped date of original discovery
            data["scraped_at"] = existing[item_id].get("scraped_at", data["scraped_at"])
            data["is_new"] = False
        
        updated_listings[item_id] = data

    # Keep any listings that were in the database but not on the first page, just in case
    for item_id, data in existing.items():
        if item_id not in updated_listings:
            data["is_new"] = False
            updated_listings[item_id] = data

    # Save to files
    save_listings(updated_listings)
    print(f"Saved {len(updated_listings)} total listings to database.")
    
    # Auto-push data updates to GitHub so GitHub Pages dashboard is updated in real-time
    # Skip if running inside GitHub Actions (handled by the workflow runner instead)
    if os.getenv("GITHUB_ACTIONS") != "true":
        import subprocess
        try:
            # Check if there are changes in listings files
            status = subprocess.run(["git", "status", "--porcelain", DATA_JSON_PATH, DATA_JS_PATH], capture_output=True, text=True)
            if status.stdout.strip():
                print("Detected changes in listings data. Committing and pushing to GitHub...")
                subprocess.run(["git", "add", DATA_JSON_PATH, DATA_JS_PATH], check=True)
                subprocess.run(["git", "commit", "-m", "Auto-update listings data"], check=True)
                subprocess.run(["git", "push"], check=True)
                print("Successfully pushed updates to GitHub.")
            else:
                print("No data changes detected. Skipping git push.")
        except Exception as e:
            print(f"Git auto-push failed: {e}")
        
    return new_additions

if __name__ == "__main__":
    new_items = scrape()
    if new_items:
        print(f"\nNOTIFICATION: {len(new_items)} new Polestar 2 listing(s) found!")
        for item in new_items:
            print(f"- [{item['source'].upper()}] {item['title']} for {item['price']} ({item['url']})")
    else:
        print("\nNo new listings found.")
