#!/usr/bin/env python3
"""
Fetch missing game images using ONLY Epic Games Content API (no Google search).
This script extracts images from Epic's official content API using product slugs.
"""

import requests
import os
import time
import re
from db_manager import DatabaseManager
from PIL import Image
from io import BytesIO

def normalize_to_slug(text):
    """
    Convert text to a slug format for comparison.
    Example: "Amnesia: The Bunker" -> "amnesia-the-bunker"
    """
    if not text:
        return ""

    # Convert to lowercase
    slug = text.lower()

    # Remove special characters and replace with hyphen or space
    slug = re.sub(r'[^\w\s-]', '', slug)

    # Replace multiple spaces/hyphens with single hyphen
    slug = re.sub(r'[\s_-]+', '-', slug)

    # Strip leading/trailing hyphens
    slug = slug.strip('-')

    return slug

def validate_image_url(image_url, game_name):
    """
    Validate that the image URL likely matches the game name.
    Extracts slug from URL and checks if game name slug appears in it.

    Args:
        image_url: The image URL to validate
        game_name: The game name to match against

    Returns:
        bool: True if validation passes, False otherwise
    """
    if not image_url or not game_name:
        return False

    # Normalize game name to slug
    game_slug = normalize_to_slug(game_name)

    # Extract filename from URL
    try:
        filename = image_url.split('/')[-1].split('?')[0]  # Get filename without query params
        filename_slug = normalize_to_slug(filename.rsplit('.', 1)[0])  # Remove extension
    except Exception:
        return False

    # Check if game slug appears in filename slug
    if game_slug in filename_slug:
        return True

    # For longer game names, check if significant portion matches
    # Split both into words and check overlap
    game_words = set(game_slug.split('-'))
    filename_words = set(filename_slug.split('-'))

    # Remove common words that don't help with matching
    common_words = {'the', 'a', 'an', 'of', 'and', 'or', 'edition', 'game', 'digital', 'pack'}
    game_words = game_words - common_words
    filename_words = filename_words - common_words

    # If no significant words left, fail
    if not game_words:
        return False

    # Calculate overlap percentage
    overlap = len(game_words & filename_words)
    overlap_pct = overlap / len(game_words)

    # Consider valid if >50% of significant words match
    return overlap_pct >= 0.5

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
            # Silent fail, try next slug
            continue

    return None

def download_image(image_url, game_id):
    """Download image, convert to JPG, and save it. Returns filename if successful."""

    if not image_url:
        return None

    try:
        # Download the image
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()

        # Open image from bytes
        img = Image.open(BytesIO(response.content))

        # Convert to RGB if needed (handles PNG transparency, RGBA, etc.)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            # Paste image on white background using alpha channel as mask
            if img.mode == 'RGBA':
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Always save as .jpg
        filename = f"{game_id}.jpg"
        filepath = os.path.join('output/images', filename)

        # Save as JPEG with optimization
        img.save(filepath, 'JPEG', quality=85, optimize=True)

        return filename

    except Exception as e:
        print(f"    Error downloading/converting image: {e}")
        return None

def main():
    """Fetch images for games using only Epic API"""

    print("=" * 70)
    print("Epic Games Image Fetcher (Epic API Only)")
    print("=" * 70)

    # Ensure images directory exists
    os.makedirs('output/images', exist_ok=True)

    # Initialize database
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

    if not games_without_images:
        print("\n✅ All games already have images!")
        return

    print("\nStarting image fetch process (Epic API only)...\n")

    successful = 0
    failed = 0
    skipped = 0

    for i, game in enumerate(games_without_images, 1):
        print(f"[{i}/{len(games_without_images)}] {game['name']}")

        # Skip if database already has an image filename (image exists in DB)
        if game.get('image_filename'):
            print(f"  ⏭️  Image already in database: {game['image_filename']}")
            skipped += 1
            continue

        # Try to fetch image URL from Epic API
        image_url = get_image_from_epic_api(game['product_slug'], game['url_slug'])

        if image_url:
            print(f"  ✓ Found image URL from Epic API")

            # Validate the Epic API image
            if validate_image_url(image_url, game['name']):
                print(f"  ✅ Validation passed")
            else:
                print(f"  ⚠️  Validation warning: May not match game name exactly")

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
            print(f"  ✗ No image found in Epic API")
            failed += 1

        # Be respectful to Epic servers
        if i < len(games_without_images):
            time.sleep(0.5)

    print("\n" + "=" * 70)
    print("Summary:")
    print("=" * 70)
    print(f"✅ Successfully fetched: {successful} images")
    print(f"⏩ Skipped (already exist): {skipped} images")
    print(f"❌ Failed: {failed} games")
    print(f"📊 Total processed: {len(games_without_images)} games")
    print("=" * 70)
    print("\nNOTE: This script only uses Epic's official API.")
    print("Older games may not be available in the API anymore.")
    print("For better coverage, use fetch_historical_images.py which")
    print("includes Google Images fallback (max 80 searches per run).")
    print("=" * 70)

if __name__ == '__main__':
    main()
