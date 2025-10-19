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

def get_tmdb_id(slug):
    url = f"{BASE_URL}/film/{slug}/"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        return None

    match = re.search(r'<body[^>]+data-tmdb-id="(\d+)"', res.text)
    return match.group(1) if match else None

def get_viewer_count(slug):
    stats_url = f"{BASE_URL}/csi/film/{slug}/stats/"
    stats_res = requests.get(stats_url, headers=HEADERS)
    if stats_res.status_code != 200:
        return None

    match = re.search(r'Watched by ([\d,]+)&nbsp;members', stats_res.text)
    return int(match.group(1).replace(",", "")) if match else None

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
        viewer_count = get_viewer_count(first_slug)

        if viewer_count is not None:
            print(f"   👀 {viewer_count} viewers")
        else:
            print("   ⚠️ Viewer count not found — stopping.")
            break

        if viewer_count < 1000:
            print(f"   🛑 Fewer than 1000 viewers — stopping.")
            break

        # Save TMDb IDs for all films on this page
        for slug in slugs:
            tmdb_id = get_tmdb_id(slug)
            if tmdb_id:
                with open(out_dir / f"{slug}.txt", "w") as f:
                    f.write(tmdb_id + "\n")
                print(f"   ✅ {slug} → {tmdb_id}")
            else:
                print(f"   ⚠️ {slug} — no TMDb ID found")
            time.sleep(0.5)  # be polite

        page += 1
        time.sleep(1)  # be polite

if __name__ == "__main__":
    main()
