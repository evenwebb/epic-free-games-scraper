#!/usr/bin/env python3
"""
Fetch images for historical games that don't have them.
Uses Epic Games Content API to retrieve game images.
"""

import requests
import os
import time
from db_manager import DatabaseManager

def get_image_from_epic_api(product_slug, url_slug):
    """
    Try to fetch game image from Epic's content API.
    Returns image URL if found, None otherwise.
    """

    # Try different slug variations
    slugs_to_try = []

    if product_slug:
        # Remove trailing paths like '/home'
        base_slug = product_slug.split('/')[0]
        slugs_to_try.append(base_slug)

    if url_slug and url_slug not in slugs_to_try:
        slugs_to_try.append(url_slug)

    for slug in slugs_to_try:
        if not slug:
            continue

        url = f"https://store-content-ipv4.ak.epicgames.com/api/en-US/content/products/{slug}"

        try:
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()

                # Try to find hero/background image
                if 'pages' in data:
                    for page in data['pages']:
                        if 'data' in page:
                            page_data = page['data']

                            # Check hero section
                            if 'hero' in page_data:
                                hero = page_data['hero']
                                if 'backgroundImageUrl' in hero:
                                    return hero['backgroundImageUrl']
                                if 'logoImage' in hero:
                                    return hero['logoImage']

                            # Check about section
                            if 'about' in page_data:
                                about = page_data['about']
                                if 'image' in about:
                                    return about['image']

                # Try alternate structure
                if 'productImageUrl' in data:
                    return data['productImageUrl']

        except Exception as e:
            print(f"    Error fetching from {url}: {e}")
            continue

    return None

def download_image(image_url, game_id):
    """Download image and save it. Returns filename if successful."""

    if not image_url:
        return None

    try:
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()

        # Determine file extension
        ext = 'jpg'
        if image_url.lower().endswith('.png'):
            ext = 'png'
        elif image_url.lower().endswith('.webp'):
            ext = 'webp'

        filename = f"{game_id}.{ext}"
        filepath = os.path.join('output/images', filename)

        with open(filepath, 'wb') as f:
            f.write(response.content)

        return filename

    except Exception as e:
        print(f"    Error downloading image: {e}")
        return None

def fetch_historical_images(limit=None, delay=0.5):
    """
    Fetch images for games that don't have them.

    Args:
        limit: Maximum number of games to process (None for all)
        delay: Delay between requests in seconds (to be respectful)
    """

    print("=" * 60)
    print("Historical Images Fetcher")
    print("=" * 60)

    db = DatabaseManager()

    # Get all games without images
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, epic_id, name, product_slug, url_slug, image_filename
            FROM games
            WHERE platform = 'PC' AND (image_filename IS NULL OR image_filename = '')
            ORDER BY created_at DESC
        """)
        games = cursor.fetchall()

    games_without_images = [dict(game) for game in games]

    print(f"\nFound {len(games_without_images)} games without images")

    if limit:
        games_without_images = games_without_images[:limit]
        print(f"Processing first {limit} games...")

    if not games_without_images:
        print("All games already have images!")
        return

    successful = 0
    failed = 0

    for i, game in enumerate(games_without_images, 1):
        print(f"\n[{i}/{len(games_without_images)}] {game['name']}")

        # Try to fetch image URL from API
        image_url = get_image_from_epic_api(game['product_slug'], game['url_slug'])

        if image_url:
            print(f"  ✓ Found image URL")

            # Download image
            filename = download_image(image_url, game['epic_id'])

            if filename:
                print(f"  ✓ Downloaded: {filename}")

                # Update database
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE games
                        SET image_filename = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (filename, game['id']))

                successful += 1
            else:
                print(f"  ✗ Failed to download")
                failed += 1
        else:
            print(f"  ✗ No image found in API")
            failed += 1

        # Be respectful to Epic's servers
        if delay > 0 and i < len(games_without_images):
            time.sleep(delay)

    print("\n" + "=" * 60)
    print(f"Complete!")
    print(f"  Successfully fetched: {successful} images")
    print(f"  Failed: {failed} games")
    print(f"  Total processed: {len(games_without_images)} games")
    print("=" * 60)

if __name__ == '__main__':
    import sys

    # Allow limiting number of games to process
    limit = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
            print(f"Processing up to {limit} games...")
        except:
            pass

    fetch_historical_images(limit=limit, delay=0.5)
