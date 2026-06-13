import requests
import os
import json

APIFY_TOKEN = os.environ["APIFY_TOKEN"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SEEN_IDS_FILE = "seen_ids.json"
MIN_PRICE = 15.0
MAX_PRICE = 100.0
MAX_LISTINGS = 25

ALLOWED_MODELS = [
    "iphone 11", "iphone 12", "iphone 13", "iphone 14", "iphone 15",
    "iphone11", "iphone12", "iphone13", "iphone14", "iphone15",
]

EXCLUDED_KEYWORDS = [
    "case", "cover", "hoesje", "bescherm",
    "repair", "reparatie", "defect", "broken", "kapot", "beschadig",
    "airpod", "spare", "onderdeel", "screenprotector",
    "charger", "oplader", "cable", "kabel", "accessoir", "accessory",
]


def send_telegram(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"Telegram send failed: {e}")


def load_seen_ids():
    if os.path.exists(SEEN_IDS_FILE):
        with open(SEEN_IDS_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen_ids(ids):
    with open(SEEN_IDS_FILE, "w") as f:
        json.dump(list(ids), f)


def fetch_items():
    resp = requests.post(
        "https://api.apify.com/v2/actors/haketa~marktplaats-scraper/run-sync-get-dataset-items",
        params={"token": APIFY_TOKEN},
        json={
            "query": "iphone",
            "platform": "marktplaats.nl",
            "minPrice": 15,
            "maxPrice": 100,
            "maxListings": MAX_LISTINGS,
            "sortBy": "SORT_INDEX",
            "sortOrder": "DECREASING",
            "scrapeDetails": False,
            "proxyConfiguration": {"useApifyProxy": True},
            "requestDelay": 500,
            "distanceMeters": 0,
        },
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()


def parse_price(val):
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val.replace("€", "").replace(",", ".").strip())
        except ValueError:
            return None
    return None


def is_match(item):
    title = (item.get("title") or "").lower()
    description = (item.get("description") or "").lower()

    if not any(model in title for model in ALLOWED_MODELS):
        return False

    if any(kw in title or kw in description for kw in EXCLUDED_KEYWORDS):
        return False

    price = parse_price(item.get("price"))
    if price is None or not (MIN_PRICE <= price <= MAX_PRICE):
        return False

    return True


def format_listing(item):
    price = parse_price(item.get("price"))
    price_str = f"{price:.0f}" if price is not None else "?"
    return (
        f"📱 <b>{item['title']}</b>\n"
        f"💶 Price: €{price_str}\n"
        f"📍 {item.get('location', '')}\n"
        f"🔗 {item['url']}"
    )


def main():
    seen_ids = load_seen_ids()
    is_first_run = len(seen_ids) == 0

    print("Fetching listings from Marktplaats via Apify...")
    items = fetch_items()
    print(f"Dataset returned {len(items)} items")

    sent = 0
    new_ids = set()

    for item in items:
        listing_id = str(item.get("listingId") or item.get("id") or "")
        if not listing_id:
            continue

        # Results are sorted newest-first. First known ID means everything
        # after it was already processed in a previous run — stop early.
        if listing_id in seen_ids:
            print(f"Reached known listing after {len(new_ids)} new items — stopping early.")
            break

        new_ids.add(listing_id)

        if is_match(item):
            send_telegram(format_listing(item))
            sent += 1

    seen_ids.update(new_ids)
    save_seen_ids(seen_ids)
    print(f"Done — {sent} new listings sent to Telegram.")

    if is_first_run:
        send_telegram("✅ Marktplaats scanner is active and running.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        send_telegram(f"❌ Marktplaats scanner error:\n{e}")
        raise
