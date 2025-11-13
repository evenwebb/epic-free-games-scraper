import json
import os
import re
import requests
import socket
import ipaddress
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from db_manager import DatabaseManager
from PIL import Image
from io import BytesIO
from urllib.parse import urlparse
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration Constants
class Config:
    """Configuration constants for security and performance"""
    # Security
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB max image size
    MAX_IMAGE_DIMENSION = 10000  # Max width/height in pixels
    ALLOWED_URL_SCHEMES = ['https']

    # Network
    IMAGE_DOWNLOAD_TIMEOUT = 10
    API_REQUEST_TIMEOUT = 30
    DOWNLOAD_CHUNK_SIZE = 8192
    MAX_DOWNLOAD_WORKERS = 10  # Parallel download workers

    # Image Processing
    IMAGE_QUALITY = 85
    IMAGE_OPTIMIZE = True

    # Paths
    OUTPUT_DIR = 'output'
    IMAGES_DIR = 'output/images'
    API_HASH_FILE = 'output/.api_hash'  # Store API response hash for early exit

    # Blocked IP ranges (prevent SSRF)
    BLOCKED_IP_RANGES = [
        ipaddress.ip_network('10.0.0.0/8'),        # Private
        ipaddress.ip_network('172.16.0.0/12'),     # Private
        ipaddress.ip_network('192.168.0.0/16'),    # Private
        ipaddress.ip_network('127.0.0.0/8'),       # Loopback
        ipaddress.ip_network('169.254.0.0/16'),    # Link-local (AWS metadata)
        ipaddress.ip_network('::1/128'),           # IPv6 loopback
        ipaddress.ip_network('fc00::/7'),          # IPv6 private
    ]

def sanitize_filename(filename):
    """
    Sanitize filename to prevent path traversal attacks.

    Security: Removes path separators, null bytes, and control characters.
    """
    if not filename:
        return 'unknown'

    # Remove path separators, null bytes, and control characters
    filename = re.sub(r'[/\\:\0\x00-\x1f]', '_', str(filename))

    # Remove leading dots and whitespace (prevent hidden files)
    filename = filename.lstrip('. ')

    # Limit length to prevent filesystem issues
    filename = filename[:200]

    # Ensure not empty after sanitization
    if not filename or filename == '_':
        filename = 'unknown'

    return filename

def validate_url(url):
    """
    Validate URL to prevent SSRF attacks.

    Security: Blocks private IPs, localhost, and non-HTTPS schemes.
    Returns: True if URL is safe, False otherwise
    """
    if not url:
        return False

    try:
        parsed = urlparse(url)

        # Check scheme (only HTTPS allowed)
        if parsed.scheme not in Config.ALLOWED_URL_SCHEMES:
            print(f"⚠️  Blocked URL with invalid scheme: {parsed.scheme}")
            return False

        # Check hostname exists
        if not parsed.hostname:
            print(f"⚠️  Blocked URL without hostname")
            return False

        # Resolve hostname to IP address
        try:
            ip_str = socket.gethostbyname(parsed.hostname)
            ip_obj = ipaddress.ip_address(ip_str)
        except (socket.gaierror, ValueError) as e:
            print(f"⚠️  Failed to resolve hostname {parsed.hostname}: {e}")
            return False

        # Check if IP is in blocked ranges
        for blocked_range in Config.BLOCKED_IP_RANGES:
            if ip_obj in blocked_range:
                print(f"⚠️  Blocked access to private/internal IP: {ip_str} ({parsed.hostname})")
                return False

        return True

    except Exception as e:
        print(f"⚠️  URL validation error: {e}")
        return False

def get_game_link(game):
    """Construct the store link for a game."""
    product_slug = game.get('productSlug')

    # Try productSlug first (most reliable)
    if product_slug:
        return f"https://store.epicgames.com/en-US/p/{product_slug}"

    # Then try pageSlug from catalogNs (human-readable and works consistently)
    mappings = game.get('catalogNs', {}).get('mappings', [])
    if mappings:
        page_slug = mappings[0].get('pageSlug')
        if page_slug:
            return f"https://store.epicgames.com/en-US/p/{page_slug}"

    # Fallback to urlSlug (may be a UUID that doesn't work)
    url_slug = game.get('urlSlug')
    if url_slug:
        return f"https://store.epicgames.com/en-US/p/{url_slug}"

    return None

def get_game_image_url(game):
    """Get the best image URL for a game."""
    key_images = game.get('keyImages', [])

    # Prefer OfferImageWide, then OfferImageTall, then Thumbnail
    for image_type in ['OfferImageWide', 'OfferImageTall', 'Thumbnail']:
        for image in key_images:
            if image.get('type') == image_type:
                return image.get('url')

    # If none of the preferred types found, return first image
    if key_images:
        return key_images[0].get('url')

    return None

@lru_cache(maxsize=128)
def format_date(iso_date):
    """Format ISO date to human-readable format. Cached for performance."""
    try:
        dt = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
        return dt.strftime('%b %d at %I:%M %p')
    except (ValueError, AttributeError, TypeError) as e:
        print(f"⚠️  Date formatting failed for '{iso_date}': {e}")
        return str(iso_date)

def is_valid_cached_image(file_path):
    """
    Check if a cached image file exists and is valid.

    Returns: True if valid cached image exists, False otherwise
    """
    if not os.path.exists(file_path):
        return False

    try:
        # Check file size (empty or too small = invalid)
        file_size = os.path.getsize(file_path)
        if file_size < 1024:  # Less than 1KB
            return False

        # Try to open and validate the image
        with Image.open(file_path) as img:
            # Verify format
            if img.format not in ['JPEG', 'JPG']:
                return False
            # Verify dimensions are reasonable
            if img.width < 50 or img.height < 50:
                return False
            # Image is valid
            return True

    except (OSError, IOError, Image.UnidentifiedImageError):
        # Image is corrupted or invalid
        return False

def download_and_convert_image(image_url, output_path, session=None):
    """
    Download an image and convert it to JPG format with optimization.

    Security: Validates URL, enforces size limits, checks dimensions.
    Performance: Streams download, caches if exists, uses session for connection pooling.
    """
    # Performance: Check if valid cached image exists
    if is_valid_cached_image(output_path):
        return True  # Skip download

    # Security: Validate URL to prevent SSRF
    if not validate_url(image_url):
        raise ValueError(f"Invalid or unsafe URL: {image_url}")

    # Use provided session or create a new requests call
    http_client = session if session else requests

    try:
        # Stream download with size limit to prevent resource exhaustion
        img_response = http_client.get(
            image_url,
            timeout=Config.IMAGE_DOWNLOAD_TIMEOUT,
            stream=True,
            allow_redirects=False  # Prevent redirect-based attacks
        )
        img_response.raise_for_status()

        # Check Content-Length header if available
        content_length = img_response.headers.get('Content-Length')
        if content_length and int(content_length) > Config.MAX_IMAGE_SIZE:
            raise ValueError(f"Image too large: {content_length} bytes (max {Config.MAX_IMAGE_SIZE})")

        # Download with size limit
        content = BytesIO()
        downloaded_bytes = 0

        for chunk in img_response.iter_content(chunk_size=Config.DOWNLOAD_CHUNK_SIZE):
            if chunk:
                downloaded_bytes += len(chunk)
                if downloaded_bytes > Config.MAX_IMAGE_SIZE:
                    raise ValueError(f"Download exceeded {Config.MAX_IMAGE_SIZE} bytes")
                content.write(chunk)

        content.seek(0)

        # Open and validate image
        img = Image.open(content)

        # Security: Validate dimensions to prevent decompression bombs
        if img.width > Config.MAX_IMAGE_DIMENSION or img.height > Config.MAX_IMAGE_DIMENSION:
            raise ValueError(f"Image dimensions too large: {img.width}x{img.height} (max {Config.MAX_IMAGE_DIMENSION})")

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

        # Save as JPEG with optimization
        img.save(output_path, 'JPEG', quality=Config.IMAGE_QUALITY, optimize=Config.IMAGE_OPTIMIZE)
        return True

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to download image from {image_url}: {e}") from e
    except (OSError, IOError) as e:
        raise RuntimeError(f"Failed to process/save image to {output_path}: {e}") from e

def compute_api_hash(response_data):
    """Compute SHA256 hash of API response for change detection."""
    return hashlib.sha256(json.dumps(response_data, sort_keys=True).encode()).hexdigest()

def load_previous_api_hash():
    """Load the previous API response hash from file."""
    try:
        if os.path.exists(Config.API_HASH_FILE):
            with open(Config.API_HASH_FILE, 'r') as f:
                return f.read().strip()
    except Exception:
        pass
    return None

def save_api_hash(hash_value):
    """Save the current API response hash to file."""
    try:
        os.makedirs(Config.OUTPUT_DIR, exist_ok=True)
        with open(Config.API_HASH_FILE, 'w') as f:
            f.write(hash_value)
    except Exception as e:
        print(f"⚠️  Failed to save API hash: {e}")

def download_image_task(image_url, image_path, game_title, session):
    """Task wrapper for parallel image downloading."""
    try:
        download_and_convert_image(image_url, image_path, session=session)
        return {'success': True, 'game': game_title, 'path': image_path}
    except Exception as e:
        return {'success': False, 'game': game_title, 'error': str(e)}

def scrape_epic_free_games():
    # Initialize database
    db = DatabaseManager()

    # Paths (using Config constants)
    os.makedirs(Config.IMAGES_DIR, exist_ok=True)

    # Performance: Load existing games from database for duplicate checking (O(1) dict lookup)
    all_games = db.get_all_games_chronological()
    existing_games_dict = {game['link']: game for game in all_games}

    new_games = []  # Track new current games
    current_games = []  # Track all current free games (for counts)
    next_games = []  # Track upcoming games
    existing_next_game_images = []  # Track images for next games

    # Performance: Create session for connection pooling
    session = requests.Session()

    try:
        # Update promotion statuses in database
        db.update_promotion_status()

        # Fetch free games from Epic Games API
        api_url = 'https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US&allowCountries=US'
        print("Fetching free games from Epic Games API...")
        response = session.get(api_url, timeout=Config.API_REQUEST_TIMEOUT)
        response.raise_for_status()

        api_data = response.json()

        # Performance: Early exit if API response unchanged
        current_hash = compute_api_hash(api_data)
        previous_hash = load_previous_api_hash()

        if current_hash == previous_hash and previous_hash is not None:
            print("✓ API response unchanged - no new data to process")
            db.record_scrape_run(
                games_found=0,
                new_games=0,
                current=0,
                upcoming=0,
                success=True
            )
            return

        print(f"API response changed - processing updates...")
        games = api_data['data']['Catalog']['searchStore']['elements']

        now = datetime.now(timezone.utc)

        # Performance: Collect data for batch database operations
        games_to_insert = []
        promotions_to_insert = []
        download_tasks = []  # Collect image download tasks for parallel execution

        # Process games
        for game in games:
            if not game.get('promotions'):
                continue

            game_title = game['title']
            game_link = get_game_link(game)

            if not game_link:
                print(f"Skipping {game_title}: no valid link found")
                continue

            # Check current promotions (free now)
            promo_offers = game['promotions'].get('promotionalOffers', [])
            if promo_offers and len(promo_offers) > 0:
                for offer_group in promo_offers:
                    for offer in offer_group.get('promotionalOffers', []):
                        start = datetime.fromisoformat(offer['startDate'].replace('Z', '+00:00'))
                        end = datetime.fromisoformat(offer['endDate'].replace('Z', '+00:00'))

                        # Only process if currently free (100% discount)
                        if start <= now <= end and offer['discountSetting']['discountPercentage'] == 0:
                            image_url = get_game_image_url(game)
                            game_id = sanitize_filename(game.get('id', game_link.split('/')[-1]))
                            date_period = f"Free Now - {format_date(offer['endDate'])}"

                            # Save image (always as JPG) - collect for parallel download
                            image_filename = None
                            image_path = None
                            if image_url:
                                image_filename = f"{game_id}.jpg"
                                image_path = os.path.join(Config.IMAGES_DIR, image_filename)
                                # Add to parallel download queue if not cached
                                if not is_valid_cached_image(image_path):
                                    download_tasks.append({
                                        'url': image_url,
                                        'path': image_path,
                                        'game': game_title,
                                        'type': 'current'
                                    })

                            # Collect game data for batch insert
                            games_to_insert.append({
                                'epic_id': game_id,
                                'name': game_title,
                                'link': game_link,
                                'platform': 'PC',
                                'image_filename': image_filename
                            })

                            # Collect promotion data for batch insert (will add game_id later)
                            promotions_to_insert.append({
                                'epic_id': game_id,  # Temporary key for lookup
                                'platform': 'PC',
                                'start_date': offer['startDate'],
                                'end_date': offer['endDate'],
                                'status': 'current'
                            })

                            # Check for duplicates using database (O(1) dict lookup)
                            if game_link not in existing_games_dict:
                                new_games.append(game_title)

                            # Track all current free games (for statistics)
                            current_games.append({
                                'Name': game_title,
                                'Link': game_link,
                                'Image': image_path,
                                'Availability': date_period
                            })

            # Check upcoming promotions (free later)
            upcoming_offers = game['promotions'].get('upcomingPromotionalOffers', [])
            if upcoming_offers and len(upcoming_offers) > 0:
                for offer_group in upcoming_offers:
                    for offer in offer_group.get('promotionalOffers', []):
                        # Only process if it will be free (100% discount)
                        if offer['discountSetting']['discountPercentage'] == 0:
                            image_url = get_game_image_url(game)
                            availability = f"{format_date(offer['startDate'])} - {format_date(offer['endDate'])}"

                            # Use epic_id for filename to ensure uniqueness and prevent cache conflicts
                            upcoming_game_id = sanitize_filename(game.get('id', game_link.split('/')[-1]))
                            image_filename = f"{upcoming_game_id}.jpg"
                            image_path = os.path.join(Config.IMAGES_DIR, image_filename)

                            if image_url:
                                # Add to parallel download queue if not cached
                                if not is_valid_cached_image(image_path):
                                    download_tasks.append({
                                        'url': image_url,
                                        'path': image_path,
                                        'game': game_title,
                                        'type': 'upcoming'
                                    })
                                # If download fails later, image_filename will be set to None
                                # For now, assume success

                            # Collect game data for batch insert
                            games_to_insert.append({
                                'epic_id': upcoming_game_id,
                                'name': game_title,
                                'link': game_link,
                                'platform': 'PC',
                                'image_filename': image_filename
                            })

                            # Collect promotion data for batch insert (will add game_id later)
                            promotions_to_insert.append({
                                'epic_id': upcoming_game_id,  # Temporary key for lookup
                                'platform': 'PC',
                                'start_date': offer['startDate'],
                                'end_date': offer['endDate'],
                                'status': 'upcoming'
                            })

                            # Track which upcoming game images are in use
                            if image_filename:
                                existing_next_game_images.append(image_filename)

                            # Add to next games
                            next_games.append({
                                'Name': game_title,
                                'Link': game_link,
                                'Image': image_path,
                                'Availability': availability
                            })

        print(f"Found {len(current_games)} current free games")
        print(f"Found {len(next_games)} upcoming free games")

        # Performance: Execute parallel image downloads
        if download_tasks:
            print(f"Downloading {len(download_tasks)} images in parallel...")
            with ThreadPoolExecutor(max_workers=Config.MAX_DOWNLOAD_WORKERS) as executor:
                # Submit all download tasks
                future_to_task = {
                    executor.submit(download_image_task, task['url'], task['path'], task['game'], session): task
                    for task in download_tasks
                }

                # Process results as they complete
                for future in as_completed(future_to_task):
                    result = future.result()
                    if result['success']:
                        print(f"✓ Downloaded: {result['game']}")
                    else:
                        print(f"✗ Failed: {result['game']} - {result['error']}")

        # Performance: Batch insert all games and promotions
        print(f"Batch inserting {len(games_to_insert)} games...")
        game_id_map = db.batch_insert_or_update_games(games_to_insert)

        # Map promotion data to game_ids and batch insert
        for promo in promotions_to_insert:
            epic_id = promo.pop('epic_id')  # Remove temporary key
            platform = promo['platform']
            promo['game_id'] = game_id_map.get((epic_id, platform))
            if not promo['game_id']:
                print(f"⚠️  Warning: Could not find game_id for {epic_id}")

        print(f"Batch inserting {len(promotions_to_insert)} promotions...")
        db.batch_insert_promotions(promotions_to_insert)

        # Cleanup old next-game images
        for filename in os.listdir(Config.IMAGES_DIR):
            # Security: Validate filename before deletion
            if (filename.startswith("next-game") and
                filename.endswith(".jpg") and
                filename not in existing_next_game_images):
                try:
                    filepath = os.path.join(Config.IMAGES_DIR, filename)
                    os.remove(filepath)
                    print(f"Removed unused file: {filename}")
                except OSError as e:
                    print(f"⚠️  Failed to remove {filename}: {e}")

        print(f"Data scraped successfully. Found {len(new_games)} new games.")

        # Performance: Save API hash for next run's early exit check
        save_api_hash(current_hash)

        # Record scrape run in database
        db.record_scrape_run(
            games_found=len(games),
            new_games=len(new_games),
            current=len(current_games),
            upcoming=len(next_games),
            success=True
        )

        # Update statistics cache
        db.update_statistics_cache()

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

        # Record failed scrape run in database
        try:
            db.record_scrape_run(
                games_found=0,
                new_games=0,
                current=0,
                upcoming=0,
                success=False,
                error=str(e)
            )
        except Exception as db_error:
            print(f"⚠️  Failed to record error in database: {db_error}")
            pass  # Don't fail if database recording fails

    finally:
        # Performance: Close session to free resources
        session.close()

if __name__ == '__main__':
    scrape_epic_free_games()
