import cloudscraper
from bs4 import BeautifulSoup
from pathlib import Path
import time
import re
import hashlib
import json
from datetime import date

BASE_URL = "https://letterboxd.com"
AJAX_POPULAR_PAGE_URL = BASE_URL + "/films/ajax/popular/page/{}/"
STATE_FILE = Path("state.txt")
MAX_RUNTIME_SECS = 50 * 60

# Create a cloudscraper session to bypass Cloudflare
session = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'darwin',
        'desktop': True
    }
)


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
    res = session.get(url)
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
    res = session.get(url)
    if res.status_code != 200:
        return None

    match = re.search(r'<body[^>]+data-tmdb-id="(\d+)"', res.text)
    return match.group(1) if match else None


def get_viewer_count(slug):
    stats_url = f"{BASE_URL}/csi/film/{slug}/stats/"
    stats_res = session.get(stats_url)
    if stats_res.status_code != 200:
        return None

    match = re.search(r"Watched by ([\d,]+)&nbsp;members", stats_res.text)
    return int(match.group(1).replace(",", "")) if match else None


def get_ratings(slug):
    """Fetch average rating and rating count from ratings-summary endpoint."""
    url = f"{BASE_URL}/csi/film/{slug}/ratings-summary/"
    res = session.get(url)
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
            print(f"\n⏱️ 10-minute runtime limit reached. Stopping.")
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

        # Save/validate TMDb IDs and ratings for all films on this page
        for slug in slugs:
            cache_path = get_cache_path(slug)
            film_data = load_film_data(cache_path, slug)

            # Fetch TMDb ID
            tmdb_id = get_tmdb_id(slug)

            if not tmdb_id:
                # No TMDb ID found - delete file if it exists
                if cache_path.exists():
                    cache_path.unlink()
                    print(f"   🗑️ {slug} — removed (no TMDb ID)")
                else:
                    print(f"   ⚠️ {slug} — no TMDb ID found")
                time.sleep(0.5)
                continue

            # Fetch ratings
            avg_rating, num_ratings = get_ratings(slug)

            # Track what changed
            tmdb_changed = film_data["tmdb_id"] != tmdb_id
            film_data["tmdb_id"] = tmdb_id

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

            time.sleep(0.5)  # be polite

        page += 1
        time.sleep(1)  # be polite

    save_state(page)


if __name__ == "__main__":
    main()
