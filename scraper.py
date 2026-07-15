import os
import json
import re
import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# Define paths
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_JSON_PATH = os.path.join(WORKSPACE_DIR, "listings.json")
DATA_JS_PATH = os.path.join(WORKSPACE_DIR, "listings.js")

URL = "https://www.facebook.com/marketplace/auckland/search/?query=polestar%202"

def load_existing_listings():
    if os.path.exists(DATA_JSON_PATH):
        try:
            with open(DATA_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading listings.json: {e}")
    return {}

def save_listings(listings):
    # Save to JSON
    with open(DATA_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(listings, f, indent=2, ensure_ascii=False)
    
    # Save to JS for local HTML client-side loading
    js_content = f"window.marketplaceListings = {json.dumps(list(listings.values()), indent=2, ensure_ascii=False)};"
    with open(DATA_JS_PATH, "w", encoding="utf-8") as f:
        f.write(js_content)

def scrape():
    print(f"Starting Facebook Marketplace scraper at {datetime.datetime.now().isoformat()}...")
    existing = load_existing_listings()
    new_additions = []
    current_listings = {}

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
        
        page = context.new_page()
        
        # Go to Facebook Marketplace search
        print(f"Navigating to: {URL}")
        page.goto(URL, wait_until="networkidle")
        
        # Wait a bit for page load
        page.wait_for_timeout(5000)
        
        # Scroll down to load more results
        print("Scrolling page to load more listings...")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        page.wait_for_timeout(3000)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)

        # Grab page HTML content
        html_content = page.content()
        
        # Save HTML for debugging if needed
        # with open(os.path.join(WORKSPACE_DIR, "debug_fb.html"), "w", encoding="utf-8") as f:
        #    f.write(html_content)

        browser.close()

    # Parse with BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Facebook Marketplace links are to /marketplace/item/<id>/
    links = soup.find_all("a", href=re.compile(r"/marketplace/item/\d+"))
    print(f"Found {len(links)} raw marketplace links on the page.")

    for link in links:
        href = link.get("href")
        # Normalize URL
        if href.startswith("/"):
            href = "https://www.facebook.com" + href
        
        # Clean URL (remove query parameters)
        url_clean = href.split("?")[0]
        
        # Extract item ID
        match = re.search(r"/marketplace/item/(\d+)", url_clean)
        if not match:
            continue
        item_id = match.group(1)
        
        if item_id in current_listings:
            continue  # Avoid duplicate entries on the page
            
        # Extract Text lines inside the anchor tag
        text_content = link.get_text(separator="\n")
        lines = [line.strip() for line in text_content.split("\n") if line.strip()]
        
        # Extract Image URL
        img = link.find("img")
        img_url = img.get("src") if img else ""

        # Facebook Marketplace cards typically display:
        # Line 0: Price (e.g. $45,000 or NZ$45,000)
        # Line 1: Title (e.g. 2021 Polestar 2)
        # Line 2: Location (e.g. Auckland, NZ)
        # Line 3: Mileage/etc (sometimes present, e.g. 15K km)
        price = "N/A"
        title = "Unknown Polestar 2"
        location = "Auckland"
        
        if len(lines) >= 1:
            # First line is usually price
            price = lines[0]
        if len(lines) >= 2:
            title = lines[1]
        if len(lines) >= 3:
            location = lines[2]
            
        # We only want Polestar 2 listings (filtering out accessories or non-Polestar 2 items if any)
        # However, let's keep it broad and do a soft check, since the query was "polestar 2"
        if "polestar" not in title.lower():
            continue

        item_data = {
            "id": item_id,
            "title": title,
            "price": price,
            "location": location,
            "url": url_clean,
            "image": img_url,
            "scraped_at": datetime.datetime.now().isoformat(),
            "is_new": False
        }
        
        current_listings[item_id] = item_data

    # Compare with existing listings
    print(f"Scraped {len(current_listings)} valid listings.")
    
    # Update listings. Set "is_new" to True for new listings
    updated_listings = {}
    for item_id, data in current_listings.items():
        if item_id not in existing:
            data["is_new"] = True
            new_additions.append(data)
            print(f"NEW LISTING FOUND: {data['title']} - {data['price']}")
        else:
            # Preserve scraped date of original discovery, but update other fields if they changed
            data["scraped_at"] = existing[item_id].get("scraped_at", data["scraped_at"])
            # Reset is_new to false (or keep true if it was new and user hasn't seen it,
            # but since this is a new run, we'll mark only items discovered *this run* as new,
            # while older items are no longer "new additions")
            data["is_new"] = False
        
        updated_listings[item_id] = data

    # Keep any listings that were in the database but not on the first page, just in case (optional,
    # but let's keep them so we don't lose history, just mark them as inactive or keep them as is)
    for item_id, data in existing.items():
        if item_id not in updated_listings:
            # Retain old listing in the DB (might be sold or just fell off the first page)
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
        print(f"NOTIFICATION: {len(new_items)} new Polestar 2 listing(s) found!")
        for item in new_items:
            print(f"- {item['title']} for {item['price']} ({item['url']})")
    else:
        print("No new listings found.")
