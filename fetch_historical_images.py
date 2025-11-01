#!/usr/bin/env python3
"""
Fetch images for historical games that don't have them.
Uses Epic Games Content API to retrieve game images.

MANUAL FALLBACK FOR MISSING IMAGES:
If a game's image can't be found via the API, you can manually search using:
  Google Images: site:store.epicgames.com [game name]

Filter results by aspect ratio to get proper hero/banner images (landscape, not square).
Ignore small thumbnails and icons - look for images 800px+ wide with 16:9 to 21:9 aspect ratio.
"""

import requests
import os
import time
import re
from urllib.parse import quote_plus
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
                                    img_url = hero['backgroundImageUrl']
                                    # Make sure it's a string, not a dict
                                    if isinstance(img_url, str) and img_url.startswith('http'):
                                        return img_url
                                if 'logoImage' in hero:
                                    img_url = hero['logoImage']
                                    if isinstance(img_url, str) and img_url.startswith('http'):
                                        return img_url

                            # Check about section
                            if 'about' in page_data:
                                about = page_data['about']
                                if 'image' in about:
                                    img_url = about['image']
                                    if isinstance(img_url, str) and img_url.startswith('http'):
                                        return img_url

                # Try alternate structure
                if 'productImageUrl' in data:
                    return data['productImageUrl']

        except Exception as e:
            print(f"    Error fetching from {url}: {e}")
            continue

    return None

def get_image_from_google(game_name):
    """
    Search Google Images for game images from store.epicgames.com.
    Uses Jina AI reader to parse Google search results.
    Filters by aspect ratio to get proper hero/banner images.
    Returns image URL if found, None otherwise.
    """

    # Construct Google Images search query
    search_query = f"site:store.epicgames.com {game_name}"
    encoded_query = quote_plus(search_query)

    # Use Jina AI reader to parse Google Images search
    jina_url = f"https://r.jina.ai/https://www.google.com/search?q={encoded_query}&tbm=isch"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        response = requests.get(jina_url, headers=headers, timeout=15)

        if response.status_code != 200:
            print(f"    Jina AI returned status {response.status_code}")
            return None

        # Parse the readable content from Jina
        content = response.text

        # Look for Epic Games image URLs in the content
        patterns = [
            r'(https://cdn[0-9]*\.epicgames\.com/[^\s\)]+\.(?:jpg|jpeg|png|webp))',
            r'(https://[^\s]*epicstatic\.com/[^\s\)]+\.(?:jpg|jpeg|png|webp))',
            r'(https://[^\s]*\.ak\.epicgames\.com/[^\s\)]+\.(?:jpg|jpeg|png|webp))'
        ]

        image_urls = []
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            image_urls.extend(matches)

        if not image_urls:
            print(f"    No image URLs found in Jina response")
            return None

        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in image_urls:
            # Clean up URL (remove trailing characters)
            url = url.rstrip('.,;)')
            if url not in seen and len(url) > 20:
                seen.add(url)
                unique_urls.append(url)

        print(f"    Found {len(unique_urls)} potential image URLs")

        # Try to filter by aspect ratio and quality indicators
        # We want landscape images (game hero/banner images)
        for url in unique_urls[:15]:  # Check first 15 images
            try:
                # Check URL for quality indicators first
                url_lower = url.lower()
                has_good_indicator = any(indicator in url_lower for indicator in
                    ['1920', '1280', '1200', 'carousel', 'hero', 'featured', 'keyart', 'wide'])

                # Skip small thumbnails
                if any(bad in url_lower for bad in ['thumbnail', 'thumb', 'small', 'icon']):
                    continue

                # Try to get image dimensions
                img_response = requests.get(url, timeout=10, stream=True)
                img_response.raise_for_status()

                img_data = img_response.content

                # Try to extract dimensions
                width, height = None, None

                # Check JPEG
                if b'\xff\xd8\xff' in img_data[:3]:
                    width, height = get_jpeg_dimensions(img_data)
                # Check PNG
                elif img_data[:8] == b'\x89PNG\r\n\x1a\n':
                    width, height = get_png_dimensions(img_data)

                if width and height:
                    aspect_ratio = width / height
                    # Look for landscape images (16:9 to 21:9 range approximately)
                    if 1.5 <= aspect_ratio <= 2.5 and width >= 800:
                        print(f"    Found suitable image: {width}x{height} (ratio: {aspect_ratio:.2f})")
                        return url
                    elif has_good_indicator and width >= 600:
                        print(f"    Found image with good URL indicator: {width}x{height}")
                        return url

            except Exception as e:
                # Skip this image and try next
                continue

        # If no suitable image found but we have URLs, return the first one with good indicators
        for url in unique_urls[:10]:
            if any(indicator in url.lower() for indicator in
                   ['1920', '1280', 'carousel', 'hero', 'featured', 'keyart']):
                print(f"    Using URL with quality indicator")
                return url

        # Last resort: return first URL
        if unique_urls:
            print(f"    Using first available URL")
            return unique_urls[0]

    except Exception as e:
        print(f"    Error searching via Jina: {e}")
        return None

    return None

def get_png_dimensions(png_data):
    """Extract dimensions from PNG data. Returns (width, height) or (None, None)."""
    try:
        if len(png_data) < 24:
            return None, None

        # PNG IHDR chunk contains dimensions
        # Skip PNG signature (8 bytes) and chunk length (4 bytes) and chunk type (4 bytes)
        width = int.from_bytes(png_data[16:20], byteorder='big')
        height = int.from_bytes(png_data[20:24], byteorder='big')
        return width, height
    except Exception:
        pass

    return None, None

def get_jpeg_dimensions(jpeg_data):
    """Extract dimensions from JPEG data. Returns (width, height) or (None, None)."""
    try:
        # JPEG markers
        i = 2  # Skip SOI marker
        while i < len(jpeg_data):
            # Find next marker
            while jpeg_data[i] != 0xFF and i < len(jpeg_data):
                i += 1

            if i >= len(jpeg_data):
                break

            marker = jpeg_data[i + 1]

            # SOF markers (Start of Frame) contain dimensions
            if 0xC0 <= marker <= 0xCF and marker not in [0xC4, 0xC8, 0xCC]:
                # Read segment length
                if i + 9 >= len(jpeg_data):
                    break

                height = (jpeg_data[i + 5] << 8) | jpeg_data[i + 6]
                width = (jpeg_data[i + 7] << 8) | jpeg_data[i + 8]
                return width, height

            # Skip to next marker
            if i + 2 >= len(jpeg_data):
                break
            seg_len = (jpeg_data[i + 2] << 8) | jpeg_data[i + 3]
            i += 2 + seg_len

    except Exception:
        pass

    return None, None

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

        # Try to fetch image URL from Epic API first
        image_url = get_image_from_epic_api(game['product_slug'], game['url_slug'])

        if image_url:
            print(f"  ✓ Found image URL from Epic API")
        else:
            print(f"  ✗ No image found in Epic API")
            print(f"  → Trying Google Images search via Jina AI...")

            # Fallback to Google Images search
            image_url = get_image_from_google(game['name'])

            if image_url:
                print(f"  ✓ Found image URL from Google Images")
            else:
                print(f"  ✗ No image found in Google Images either")

        if image_url:
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
            failed += 1

        # Be respectful to servers
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
