import requests
from bs4 import BeautifulSoup
from pathlib import Path
import time
import re

BASE_URL = "https://letterboxd.com"
POPULAR_URL = BASE_URL + "/films/popular/page/{}/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
}

def get_film_slugs_from_page(page_number):
    res = requests.get(POPULAR_URL.format(page_number), headers=HEADERS)
    if res.status_code != 200:
        return []
    soup = BeautifulSoup(res.text, "html.parser")
    films = soup.select("li.poster-container a.film-poster")
    slugs = []
    for a in films:
        href = a.get("href")
        if href and href.startswith("/film/"):
            slug = href.strip("/").split("/")[1]
            slugs.append(slug)
    return slugs

def get_film_data(slug):
    url = f"{BASE_URL}/film/{slug}/"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        print(f"❌ Failed to fetch {slug}")
        return None, None
    soup = BeautifulSoup(res.text, "html.parser")

    # TMDb ID
    body = soup.find("body")
    tmdb_id = body["data-tmdb-id"] if body and body.has_attr("data-tmdb-id") else None

    # Viewer count (extract from "Watched by X people" text)
    stats_section = soup.select_one("section#featured-film-header")
    viewer_count = None
    if stats_section:
        text = stats_section.get_text()
        match = re.search(r"Watched by ([\d,]+) people", text)
        if match:
            viewer_count = int(match.group(1).replace(",", ""))

    return tmdb_id, viewer_count

def main():
    out_dir = Path("cache")
    out_dir.mkdir(exist_ok=True)

    page = 1
    stop = False

    while not stop:
        print(f"\n📄 Processing popular films page {page}...")
        slugs = get_film_slugs_from_page(page)
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
