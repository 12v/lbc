import requests
from pathlib import Path
import time
import re

BASE_URL = "https://letterboxd.com"
AJAX_POPULAR_URL = BASE_URL + "/films/ajax/popular/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
}

def get_popular_films():
    res = requests.get(AJAX_POPULAR_URL, headers=HEADERS)
    print(f"→ GET {AJAX_POPULAR_URL} → {res.status_code}")
    if res.status_code != 200:
        return []
    data = res.json()
    # 'films' is a list of dicts with film info
    return data.get("films", [])

def get_film_data(slug):
    url = f"{BASE_URL}/film/{slug}/"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        print(f"❌ Failed to fetch {slug}")
        return None, None
    # Extract tmdb id from body[data-tmdb-id]
    match = re.search(r'<body[^>]+data-tmdb-id="(\d+)"', res.text)
    tmdb_id = match.group(1) if match else None

    # Extract viewer count from "Watched by X people" text
    match = re.search(r"Watched by ([\d,]+) people", res.text)
    viewer_count = int(match.group(1).replace(",", "")) if match else None

    return tmdb_id, viewer_count

def main():
    out_dir = Path("cache")
    out_dir.mkdir(exist_ok=True)

    print(f"\n📄 Fetching popular films from AJAX endpoint...")
    films = get_popular_films()

    if not films:
        print("No films found in AJAX response.")
        return

    for film in films:
        slug = film.get("slug")
        if not slug:
            continue

        print(f"→ Fetching data for {slug}...")
        tmdb_id, viewer_count = get_film_data(slug)

        if viewer_count is not None:
            print(f"   👀 {viewer_count} viewers")
        else:
            print("   ⚠️ Viewer count not found — skipping")
            continue

        if viewer_count < 1000:
            print(f"   🛑 Fewer than 1000 viewers — stopping.")
            break

        if tmdb_id:
            with open(out_dir / f"{slug}.txt", "w") as f:
                f.write(tmdb_id + "\n")
            print(f"   ✅ Saved TMDb ID {tmdb_id}")
        else:
            print(f"   ⚠️ No TMDb ID found for {slug}")

        time.sleep(0.5)  # be polite

if __name__ == "__main__":
    main()
