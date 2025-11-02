#!/usr/bin/env python3
"""
Fetch images for historical games that don't have them.
Uses Epic Games Content API as primary source and Google Images as fallback.

MANUAL FALLBACK FOR MISSING IMAGES:
If a game's image can't be found automatically, you can manually search using:
  Google Images: site:store.epicgames.com [game name]

Filter results by aspect ratio to get proper hero/banner images (landscape, not square).
Ignore small thumbnails and icons - look for images 800px+ wide with 16:9 to 21:9 aspect ratio.
"""

import requests
import os
import time
import re
import json
import random
from urllib.parse import quote, quote_plus
from db_manager import DatabaseManager

# User agents for rotation to avoid bot detection
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0'
]

# Google search rate limiting
GOOGLE_SEARCH_LIMIT = 80  # Stop using Google after this many searches
GOOGLE_SEARCH_DELAY_MIN = 2  # Minimum seconds between Google requests
GOOGLE_SEARCH_DELAY_MAX = 5  # Maximum seconds between Google requests

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

def get_image_from_google(game_name, google_request_count=0):
    """
    Search Google Images for game images from store.epicgames.com.
    Directly scrapes Google Images HTML to extract image URLs.
    Filters by aspect ratio to get proper hero/banner images.

    Args:
        game_name: Name of the game to search for
        google_request_count: Number of Google searches made so far (for rate limiting)

    Returns tuple: (image_url, rate_limited)
        - image_url: URL if found, None otherwise
        - rate_limited: True if Google returned 429, False otherwise
    """

    # Check if we've hit the Google search limit
    if google_request_count >= GOOGLE_SEARCH_LIMIT:
        print(f"    Google search limit reached ({GOOGLE_SEARCH_LIMIT}), skipping")
        return None, False

    # Rotate user agent to avoid detection
    user_agent = random.choice(USER_AGENTS)

    headers = {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    try:
        # Construct Google Images search query
        search_query = f"store.epicgames.com {game_name}"
        encoded_query = quote_plus(search_query)

        # Direct Google Images request
        google_url = f"https://www.google.com/search?q={encoded_query}&tbm=isch"

        response = requests.get(google_url, headers=headers, timeout=15)

        if response.status_code == 429:
            print(f"    ⚠️  Google rate limit hit (429) - stopping Google searches")
            return None, True

        if response.status_code != 200:
            print(f"    Google returned status {response.status_code}")
            return None, False

        # Parse HTML content
        content = response.text

        # Look for Epic Games image URLs in the HTML
        # Google embeds image data in JavaScript, look for various patterns
        patterns = [
            r'"(https://cdn[0-9]*\.epicgames\.com/[^"]+\.(?:jpg|jpeg|png|webp))"',
            r'"(https://[^"]*epicstatic\.com/[^"]+\.(?:jpg|jpeg|png|webp))"',
            r'"(https://[^"]*\.ak\.epicgames\.com/[^"]+\.(?:jpg|jpeg|png|webp))"',
            r'\["(https://cdn[0-9]*\.epicgames\.com/[^"]+\.(?:jpg|jpeg|png|webp))',
            r'\["(https://[^"]*epicstatic\.com/[^"]+\.(?:jpg|jpeg|png|webp))',
            r'\["(https://[^"]*\.ak\.epicgames\.com/[^"]+\.(?:jpg|jpeg|png|webp))'
        ]

        image_urls = []
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            image_urls.extend(matches)

        if not image_urls:
            print(f"    No image URLs found in Google response")
            return None, False

        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in image_urls:
            # Clean up URL (remove trailing characters and escape sequences)
            url = url.replace('\\u003d', '=').replace('\\u0026', '&')
            url = url.rstrip('.,;)')
            if url not in seen and len(url) > 20:
                seen.add(url)
                unique_urls.append(url)

        print(f"    Found {len(unique_urls)} potential image URLs")

        # Try to filter by aspect ratio and quality indicators
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
                        return url, False
                    elif has_good_indicator and width >= 600:
                        print(f"    Found image with good URL indicator: {width}x{height}")
                        return url, False

            except Exception as e:
                # Skip this image and try next
                continue

        # If no suitable image found but we have URLs, return the first one with good indicators
        for url in unique_urls[:10]:
            if any(indicator in url.lower() for indicator in
                   ['1920', '1280', 'carousel', 'hero', 'featured', 'keyart']):
                print(f"    Using URL with quality indicator")
                return url, False

        # Last resort: return first URL
        if unique_urls:
            print(f"    Using first available URL")
            return unique_urls[0], False

    except Exception as e:
        print(f"    Error searching Google Images: {e}")
        return None, False

    return None, False

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
    skipped = 0
    google_request_count = 0  # Track Google searches for rate limiting
    google_rate_limited = False  # Flag to stop Google searches after 429

    for i, game in enumerate(games_without_images, 1):
        print(f"\n[{i}/{len(games_without_images)}] {game['name']}")

        # Check if image file already exists on disk
        if game.get('image_filename'):
            image_path = os.path.join('output/images', game['image_filename'])
            if os.path.exists(image_path):
                print(f"  ⏭️  Image already exists: {game['image_filename']}")
                skipped += 1
                continue

        # Try to fetch image URL from Epic API first
        image_url = get_image_from_epic_api(game['product_slug'], game['url_slug'])
        used_google = False

        if image_url:
            print(f"  ✓ Found image URL from Epic API")
        else:
            print(f"  ✗ No image found in Epic API")

            # Only try Google if not rate limited yet
            if not google_rate_limited:
                print(f"  → Trying Google Images search... (Google requests: {google_request_count}/{GOOGLE_SEARCH_LIMIT})")

                # Fallback to Google Images search
                image_url, rate_limited = get_image_from_google(game['name'], google_request_count)
                used_google = True
                google_request_count += 1

                # If we hit rate limit, stop future Google searches
                if rate_limited:
                    google_rate_limited = True
                    print(f"  ⚠️  Google rate limit detected - will skip Google for remaining games")

                if image_url:
                    print(f"  ✓ Found image URL from Google Images")
                else:
                    if not rate_limited:
                        print(f"  ✗ No image found in Google Images either")
            else:
                print(f"  ⏭️  Skipping Google search (rate limited)")

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

        # Add delay after Google searches to avoid rate limiting
        if used_google and i < len(games_without_images):
            delay_time = random.uniform(GOOGLE_SEARCH_DELAY_MIN, GOOGLE_SEARCH_DELAY_MAX)
            print(f"  ⏳ Waiting {delay_time:.1f}s before next request...")
            time.sleep(delay_time)
        # Be respectful to Epic servers
        elif delay > 0 and i < len(games_without_images):
            time.sleep(delay)

    print("\n" + "=" * 60)
    print(f"Complete!")
    print(f"  Successfully fetched: {successful} images")
    print(f"  Skipped (already exist): {skipped} images")
    print(f"  Failed: {failed} games")
    print(f"  Google searches made: {google_request_count}")
    if google_rate_limited:
        print(f"  ⚠️  Google rate limit was hit during execution")
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
