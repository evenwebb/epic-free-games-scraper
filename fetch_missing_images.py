#!/usr/bin/env python3
"""
Fetch images for games that are missing them.
Uses SteamGridDB API - returns proper Epic Games Store format (920x430 landscape).
Requires: STEAMGRIDDB_API_KEY (free at https://www.steamgriddb.com/profile/preferences)
"""

import os
import sys
import time
import requests
from PIL import Image
from db_manager import DatabaseManager
from scrape_epic_games import (
    Config,
    download_and_convert_image,
    is_valid_cached_image,
)

# Match existing Epic-sourced images (1280x720 = 16:9)
TARGET_SIZE = (1280, 720)


def resize_to_standard(image_path):
    """Resize image to 1280x720 (16:9) to match other Epic-sourced images."""
    try:
        with Image.open(image_path) as img:
            if img.size == TARGET_SIZE:
                return
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img = img.resize(TARGET_SIZE, Image.Resampling.LANCZOS)
            img.save(image_path, 'JPEG', quality=85, optimize=True)
    except Exception:
        pass


def fetch_from_steamgriddb(epic_id, api_key):
    """Fetch grid image URL from SteamGridDB for Epic Games Store offer."""
    headers = {'Authorization': f'Bearer {api_key}'}
    r = requests.get(
        f'https://www.steamgriddb.com/api/v2/grids/egs/{epic_id}',
        headers=headers,
        params={'dimensions': '920x430'},
        timeout=10
    )
    if r.status_code != 200:
        return None
    data = r.json()
    if not data.get('success') or not data.get('data'):
        return None
    grids = data['data']
    return grids[0].get('url') if grids else None


def fetch_from_steamgriddb_by_name(name, api_key):
    """Fallback: search SteamGridDB by game name, get landscape grid (920x430)."""
    headers = {'Authorization': f'Bearer {api_key}'}
    search_term = name.split(' - ')[0].split(':')[0].strip()  # e.g. "Styx" or "Rustler"
    r = requests.get(
        f'https://www.steamgriddb.com/api/v2/search/autocomplete/{requests.utils.quote(search_term)}',
        headers=headers,
        timeout=10
    )
    if r.status_code != 200:
        return None
    data = r.json()
    if not data.get('success') or not data.get('data'):
        return None
    # Find best match: exact, then prefix match (e.g. "Styx: Shards of Darkness" for "Styx: Shards of Darkness - Deluxe")
    name_lower = name.lower()
    name_base = name_lower.split(' - ')[0].strip()  # drop " - Deluxe Edition" etc
    candidates = data['data']
    best = None
    for c in candidates:
        cn = (c.get('name') or '').lower()
        if cn == name_lower or cn == name_base:
            best = c
            break
        if name_base.startswith(cn) or cn.startswith(name_base.split(':')[0]):
            best = c
            break
    if not best:
        best = candidates[0] if candidates else None
    if not best:
        return None
    game_id = best.get('id')
    r2 = requests.get(
        f'https://www.steamgriddb.com/api/v2/grids/game/{game_id}',
        headers=headers,
        params={'dimensions': '920x430'},
        timeout=10
    )
    if r2.status_code != 200:
        return None
    data2 = r2.json()
    if not data2.get('success') or not data2.get('data'):
        return None
    return data2['data'][0].get('url')

def fetch_from_epic_store(game_link):
    """Try to get OfferImageWide from Epic store by product slug. Works only for games in catalog."""
    try:
        # Extract slug from store link: .../p/slug
        slug = game_link.rstrip('/').split('/p/')[-1]
        if not slug:
            return None
        # Epic store backend - search by slug in free games catalog
        r = requests.get(
            'https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions',
            params={'locale': 'en-GB', 'country': 'GB', 'allowCountries': 'GB'},
            timeout=15
        )
        r.raise_for_status()
        data = r.json()
        games = data.get('data', {}).get('Catalog', {}).get('searchStore', {}).get('elements', [])
        for g in games:
            # Match by productSlug or pageSlug from catalogNs
            if g.get('productSlug') == slug:
                return _get_offer_image_wide(g)
            mappings = g.get('catalogNs', {}).get('mappings', [])
            if any(m.get('pageSlug') == slug for m in mappings):
                return _get_offer_image_wide(g)
        return None
    except Exception:
        return None


def _get_offer_image_wide(game):
    """Extract OfferImageWide URL from game data (Epic's landscape format)."""
    for img in game.get('keyImages', []):
        if img.get('type') == 'OfferImageWide':
            return img.get('url')
    for img in game.get('keyImages', []):
        if img.get('type') in ('OfferImageTall', 'Thumbnail', 'featuredMedia'):
            return img.get('url')
    if game.get('keyImages'):
        return game['keyImages'][0].get('url')
    return None


def main():
    db = DatabaseManager()
    os.makedirs(Config.IMAGES_DIR, exist_ok=True)

    all_games = db.get_all_games_chronological(platform='PC')
    missing = []
    for g in all_games:
        if not g.get('image_filename'):
            missing.append(g)
        else:
            path = os.path.join(Config.IMAGES_DIR, g['image_filename'])
            if not is_valid_cached_image(path):
                missing.append(g)

    if not missing:
        print("No games missing images.")
        return

    api_key = os.environ.get('STEAMGRIDDB_API_KEY')
    if not api_key:
        print("Set STEAMGRIDDB_API_KEY for games not in Epic's free catalog.")
        print("Free key: https://www.steamgriddb.com/profile/preferences")
        sys.exit(1)

    print(f"Fetching images for {len(missing)} games from SteamGridDB (Epic store format)...")
    updated = 0
    for game in missing:
        epic_id = game['epic_id']
        name = game['name']
        link = game.get('link', '')
        url = None
        # 1. Try Epic free games API (games still in catalog)
        if link:
            url = fetch_from_epic_store(link)
        # 2. SteamGridDB by Epic ID
        if not url:
            url = fetch_from_steamgriddb(epic_id, api_key)
        # 3. SteamGridDB by name (fallback when Epic ID not in SGDB)
        if not url:
            url = fetch_from_steamgriddb_by_name(name, api_key)
        if not url:
            print(f"  ✗ No image: {name}")
            continue
        out_path = os.path.join(Config.IMAGES_DIR, f"{epic_id}.jpg")
        try:
            download_and_convert_image(url, out_path)
            resize_to_standard(out_path)
            with db.get_connection() as conn:
                conn.execute(
                    "UPDATE games SET image_filename = ?, updated_at = CURRENT_TIMESTAMP WHERE epic_id = ? AND platform = 'PC'",
                    (f"{epic_id}.jpg", epic_id)
                )
            print(f"  ✓ {name}")
            updated += 1
        except Exception as e:
            print(f"  ✗ {name}: {e}")
        time.sleep(0.5)  # Rate limit SteamGridDB

    print(f"\nUpdated {updated} games. Run generate_website.py to refresh the site.")

def force_refetch(epic_ids):
    """Force re-fetch images for specific games (e.g. wrong ratio). Deletes existing, fetches from store."""
    api_key = os.environ.get('STEAMGRIDDB_API_KEY')
    if not api_key:
        print("Set STEAMGRIDDB_API_KEY")
        sys.exit(1)
    db = DatabaseManager()
    os.makedirs(Config.IMAGES_DIR, exist_ok=True)
    games = [g for g in db.get_all_games_chronological(platform='PC') if g['epic_id'] in epic_ids]
    if not games:
        print("No matching games found.")
        return
    for game in games:
        epic_id = game['epic_id']
        path = os.path.join(Config.IMAGES_DIR, f"{epic_id}.jpg")
        if os.path.exists(path):
            os.remove(path)
        url = (
            fetch_from_epic_store(game.get('link', ''))
            or fetch_from_steamgriddb(epic_id, api_key)
            or fetch_from_steamgriddb_by_name(game['name'], api_key)
        )
        if url:
            try:
                download_and_convert_image(url, path)
                resize_to_standard(path)
                with db.get_connection() as conn:
                    conn.execute(
                        "UPDATE games SET image_filename = ?, updated_at = CURRENT_TIMESTAMP WHERE epic_id = ? AND platform = 'PC'",
                        (f"{epic_id}.jpg", epic_id)
                )
                print(f"  ✓ {game['name']}")
            except Exception as e:
                print(f"  ✗ {game['name']}: {e}")
        else:
            print(f"  ✗ {game['name']}: no image found")


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--re-fetch':
        ids = sys.argv[2:]
        if ids:
            print("Re-fetching from Epic store / SteamGridDB...")
            force_refetch(ids)
        else:
            print("Usage: python fetch_missing_images.py --re-fetch <epic_id> [epic_id ...]")
    else:
        main()
