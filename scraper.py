import requests
from bs4 import BeautifulSoup
from pathlib import Path
import time
import re

BASE_URL = "https://letterboxd.com"
AJAX_POPULAR_PAGE_URL = BASE_URL + "/films/ajax/popular/page/{}/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
}

def get_film_slugs_from_ajax_page(page):
    url = AJAX_POPULAR_PAGE_URL.format(page)
    res = requests.get(url, headers=HEADERS)
    print(f"→ GET {url} → {res.status_code}")
    if res.status_code != 200:
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    poster_items = soup.select("li.posteritem")

    slugs = []
    for li in poster_items:
        slug = li.get("data-item-slug")
        if slug:
            slugs.append(slug)
    return slugs

def get_film_data(slug):
    url = f"{BASE_URL}/film/{slug}/"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        print(f"❌ Failed to fetch {slug}")
        return None, None

    match = re.search(r'<body[^>]+data-tmdb-id="(\d+)"', res.text)
    tmdb_id = match.group(1) if match else None

    match = re.search(r"Watched by ([\d,]+) people", res.text)
    viewer_count = int(match.group(1).replace(",", "")) if match else None

    return tmdb_id, viewer_count

def main():
    out_dir = Path("cache")
    out_dir.mkdir(exist_ok=True)

    page = 1
    stop = False

    while not stop:
        print(f"\n📄 Processing AJAX popular films page {page}...")
        slugs = get_film_slugs_from_ajax_page(page)

        if not slugs:
            print("No more films found — ending scrape.")
            break

        for slug in slugs:
            print(f"→ Fetching data for {slug}...")
            tmdb_id, viewer_count = get_film_data(slug)

            if viewer_count is not None:
                print(f"   👀 {viewer_count} viewers")
            else:
                print("   ⚠️ Viewer count not found — skipping")
                continue

            if viewer_count < 1000:
                print(f"   🛑 Fewer than 1000 viewers — stopping.")
                stop = True
                break

            if tmdb_id:
                with open(out_dir / f"{slug}.txt", "w") as f:
                    f.write(tmdb_id + "\n")
                print(f"   ✅ Saved TMDb ID {tmdb_id}")
            else:
                print(f"   ⚠️ No TMDb ID found for {slug}")

            time.sleep(0.5)  # be polite

        page += 1
        time.sleep(1)  # be polite

if __name__ == "__main__":
    main()
