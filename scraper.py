import cloudscraper
from bs4 import BeautifulSoup
from pathlib import Path
import time
import re
import hashlib
import json
import random
from datetime import date

BASE_URL = "https://letterboxd.com"
AJAX_POPULAR_PAGE_URL = BASE_URL + "/films/ajax/popular/page/{}/"
STATE_FILE = Path("state.txt")
MAX_RUNTIME_SECS = 60 * 60

# Randomized delays to appear more human-like
DELAY_BETWEEN_FILMS = (1.0, 3.0)  # Random delay between films (min, max seconds)
DELAY_BETWEEN_PAGES = (2.0, 5.0)  # Random delay between pages
DELAY_BETWEEN_REQUESTS = (0.3, 0.8)  # Random delay between individual requests for same film

# User agent rotation for more natural requests
USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
]

# Create a cloudscraper session to bypass Cloudflare
session = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    },
    delay=10
)


def random_delay(delay_range):
    """Sleep for a random duration within the given range."""
    delay = random.uniform(delay_range[0], delay_range[1])
    time.sleep(delay)


def get_with_random_ua(url, retries=3):
    """Make a request with a random user agent and realistic headers."""
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0',
    }

    for attempt in range(retries):
        try:
            response = session.get(url, headers=headers, timeout=30)
            if response.status_code == 403 and attempt < retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"   ⚠️ Got 403, waiting {wait_time}s before retry {attempt + 2}/{retries}...")
                time.sleep(wait_time)
                continue
            return response
        except Exception as e:
            if attempt < retries - 1:
                print(f"   ⚠️ Request failed: {e}, retrying...")
                time.sleep(2)
                continue
            raise

    return response


def get_cache_path(slug):
    """Get cache file path for slug using MD5 hash prefix."""
    hash_hex = hashlib.md5(slug.encode()).hexdigest()
    prefix = hash_hex[:2]
    docs_dir = Path("docs") / prefix
    docs_dir.mkdir(parents=True, exist_ok=True)
    return docs_dir / f"{slug}.json"


def load_state():
    """Load current page number from state file."""
    if STATE_FILE.exists():
        try:
            page = int(STATE_FILE.read_text().strip())
            print(f"Resuming from page {page}...")
            return page
        except (ValueError, IOError):
            pass
    return 1


def save_state(page):
    """Save current page number to state file."""
    STATE_FILE.write_text(str(page))


def get_film_slugs_from_ajax_page(page):
    url = AJAX_POPULAR_PAGE_URL.format(page)
    res = get_with_random_ua(url)
    print(f"→ GET {url} → {res.status_code}")
    if res.status_code != 200:
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    poster_items = soup.select("li.posteritem")

    slugs = []
    for li in poster_items:
        react_div = li.find("div", class_="react-component")
        if react_div:
            slug = react_div.get("data-item-slug")
            if slug:
                slugs.append(slug)
    return slugs


def get_tmdb_id(slug):
    url = f"{BASE_URL}/film/{slug}/"
    res = get_with_random_ua(url)
    if res.status_code != 200:
        return None

    match = re.search(r'<body[^>]+data-tmdb-id="(\d+)"', res.text)
    return match.group(1) if match else None


def get_viewer_count(slug):
    stats_url = f"{BASE_URL}/csi/film/{slug}/stats/"
    stats_res = get_with_random_ua(stats_url)
    if stats_res.status_code != 200:
        return None

    match = re.search(r"Watched by ([\d,]+)&nbsp;members", stats_res.text)
    return int(match.group(1).replace(",", "")) if match else None


def get_ratings(slug):
    """Fetch average rating and rating count from ratings-summary endpoint."""
    url = f"{BASE_URL}/csi/film/{slug}/ratings-summary/"
    res = get_with_random_ua(url)
    if res.status_code != 200:
        return None, None

    soup = BeautifulSoup(res.text, "html.parser")
    rating_link = soup.select_one("span.average-rating a")
    if not rating_link:
        return None, None

    title_attr = rating_link.get("title", "")
    match = re.search(r'Weighted average of ([\d.]+) based on ([\d,]+) ratings', title_attr)
    if match:
        avg_rating = float(match.group(1))
        num_ratings = int(match.group(2).replace(",", ""))
        return avg_rating, num_ratings

    return None, None


def load_film_data(cache_path, slug):
    """Load existing film data from JSON file, or return empty structure if not exists."""
    if cache_path.exists():
        try:
            with open(cache_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    return {
        "tmdb_id": None,
        "slug": slug,
        "ratings": []
    }


def save_film_data(cache_path, film_data):
    """Save film data to JSON file."""
    temp_path = cache_path.with_suffix(".tmp")
    with open(temp_path, "w") as f:
        json.dump(film_data, f, indent=2)
    temp_path.rename(cache_path)


def add_rating_entry(film_data, avg_rating, num_ratings):
    """Add or update rating entry for current date. Returns True if changed."""
    today = date.today().isoformat()

    # Check if entry exists for today
    for entry in film_data["ratings"]:
        if entry["date"] == today:
            # Update existing entry
            changed = entry["avg"] != avg_rating or entry["count"] != num_ratings
            entry["avg"] = avg_rating
            entry["count"] = num_ratings
            return changed

    # Add new entry
    film_data["ratings"].append({
        "date": today,
        "avg": avg_rating,
        "count": num_ratings
    })
    film_data["ratings"].sort(key=lambda x: x["date"])
    return True


def main():
    Path("docs").mkdir(exist_ok=True)

    start_time = time.time()
    page = load_state()

    while True:
        elapsed = time.time() - start_time
        if elapsed > MAX_RUNTIME_SECS:
            print(f"\n⏱️ Runtime limit reached. Stopping.")
            break

        print(f"\n📄 Processing AJAX popular films page {page}...")
        slugs = get_film_slugs_from_ajax_page(page)

        if not slugs:
            print("No more films found — resetting to page 1.")
            page = 1
            break

        # Check viewer count for first film to determine if we should continue
        first_slug = slugs[0]
        print(f"→ Checking viewer count for {first_slug}...")
        viewer_count = get_viewer_count(first_slug)

        if viewer_count is not None:
            print(f"   👀 {viewer_count} viewers")
        else:
            print("   ⚠️ Viewer count not found — stopping.")
            break

        if viewer_count < 1000:
            print(f"   🛑 Fewer than 1000 viewers — resetting to page 1.")
            page = 1
            break

        # Small pause before processing films
        random_delay(DELAY_BETWEEN_REQUESTS)

        # Save/validate TMDb IDs and ratings for all films on this page
        for slug in slugs:
            cache_path = get_cache_path(slug)
            film_data = load_film_data(cache_path, slug)

            # Use cached TMDb ID if available, otherwise fetch it
            tmdb_changed = False
            if film_data["tmdb_id"]:
                tmdb_id = film_data["tmdb_id"]
            else:
                tmdb_id = get_tmdb_id(slug)
                if not tmdb_id:
                    # No TMDb ID found - delete file if it exists
                    if cache_path.exists():
                        cache_path.unlink()
                        print(f"   🗑️ {slug} — removed (no TMDb ID)")
                    else:
                        print(f"   ⚠️ {slug} — no TMDb ID found")
                    random_delay(DELAY_BETWEEN_FILMS)
                    continue
                tmdb_changed = True
                film_data["tmdb_id"] = tmdb_id
                # Small delay between requests for same film
                random_delay(DELAY_BETWEEN_REQUESTS)

            # Fetch ratings
            avg_rating, num_ratings = get_ratings(slug)

            rating_changed = False
            if avg_rating is not None and num_ratings is not None:
                rating_changed = add_rating_entry(film_data, avg_rating, num_ratings)

            # Save updated data
            save_film_data(cache_path, film_data)

            # Print status
            if avg_rating is not None and num_ratings is not None:
                if tmdb_changed or rating_changed:
                    print(f"   ✅ {slug} → TMDb:{tmdb_id} | ⭐{avg_rating} ({num_ratings:,} ratings)")
                else:
                    print(f"   ✓ {slug} → TMDb:{tmdb_id} | ⭐{avg_rating} ({num_ratings:,} ratings) (unchanged)")
            else:
                if tmdb_changed:
                    print(f"   ✅ {slug} → TMDb:{tmdb_id} | ⚠️ no ratings")
                else:
                    print(f"   ✓ {slug} → TMDb:{tmdb_id} | ⚠️ no ratings (unchanged)")

            # Random delay between films
            random_delay(DELAY_BETWEEN_FILMS)

        # Random delay between pages
        random_delay(DELAY_BETWEEN_PAGES)
        page += 1

    save_state(page)


if __name__ == "__main__":
    main()
