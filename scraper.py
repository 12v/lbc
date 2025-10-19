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
        react_div = li.find("div", class_="react-component")
        if react_div:
            slug = react_div.get("data-item-slug")
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

    # Get viewer count from stats endpoint
    stats_url = f"{BASE_URL}/csi/film/{slug}/stats/"
    stats_res = requests.get(stats_url, headers=HEADERS)
    viewer_count = None
    if stats_res.status_code == 200:
        match = re.search(r'Watched by ([\d,]+)&nbsp;members', stats_res.text)
        viewer_count = int(match.group(1).replace(",", "")) if match else None

    return tmdb_id, viewer_count

def main():
    out_dir = Path("cache")
    out_dir.mkdir(exist_ok=True)

    page = 1

    while True:
        print(f"\n📄 Processing AJAX popular films page {page}...")
        slugs = get_film_slugs_from_ajax_page(page)

        if not slugs:
            print("No more films found — ending scrape.")
            break

        # Check viewer count for first film to determine if we should continue
        first_slug = slugs[0]
        print(f"→ Checking viewer count for {first_slug}...")
        tmdb_id, viewer_count = get_film_data(first_slug)

        if viewer_count is not None:
            print(f"   👀 {viewer_count} viewers")
        else:
            print("   ⚠️ Viewer count not found — stopping.")
            break

        if viewer_count < 1000:
            print(f"   🛑 Fewer than 1000 viewers — stopping.")
            break

        # Save TMDb ID for first film
        if tmdb_id:
            with open(out_dir / f"{first_slug}.txt", "w") as f:
                f.write(tmdb_id + "\n")
            print(f"   ✅ Saved TMDb ID {tmdb_id}")
        else:
            print(f"   ⚠️ No TMDb ID found for {first_slug}")

        page += 1
        time.sleep(1)  # be polite

if __name__ == "__main__":
    main()
