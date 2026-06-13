"""Epic Games Store API client: URL validation, data extraction, hashing."""

import hashlib
import ipaddress
import json
import os
import re
import socket
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urlparse

import epic_config


class Config:
    """Configuration constants for security and performance."""
    MAX_IMAGE_SIZE = 10 * 1024 * 1024
    MAX_IMAGE_DIMENSION = 10000
    ALLOWED_URL_SCHEMES = ['https']
    IMAGE_DOWNLOAD_TIMEOUT = 10
    API_REQUEST_TIMEOUT = 30
    DOWNLOAD_CHUNK_SIZE = 8192
    MAX_DOWNLOAD_WORKERS = 10
    IMAGE_QUALITY = 85
    IMAGE_OPTIMIZE = True
    OUTPUT_DIR = 'output'
    IMAGES_DIR = 'output/images'
    API_HASH_FILE = 'output/.api_hash'
    SCRAPE_SUMMARY_FILE = 'output/scrape_run_summary.json'

    BLOCKED_IP_RANGES = [
        ipaddress.ip_network('10.0.0.0/8'),
        ipaddress.ip_network('172.16.0.0/12'),
        ipaddress.ip_network('192.168.0.0/16'),
        ipaddress.ip_network('127.0.0.0/8'),
        ipaddress.ip_network('169.254.0.0/16'),
        ipaddress.ip_network('::1/128'),
        ipaddress.ip_network('fc00::/7'),
        ipaddress.ip_network('fe80::/10'),
    ]


def sanitize_filename(filename):
    """Sanitize filename to prevent path traversal attacks."""
    if not filename:
        return 'unknown'
    filename = re.sub(r'[/\\:\0\x00-\x1f]', '_', str(filename))
    filename = filename.lstrip('. ')
    filename = filename[:200]
    if not filename or filename == '_':
        filename = 'unknown'
    return filename


def validate_url(url):
    """Validate URL to prevent SSRF attacks. Returns True if URL is safe."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme not in Config.ALLOWED_URL_SCHEMES:
            print(f"Blocked URL with invalid scheme: {parsed.scheme}")
            return False
        if not parsed.hostname:
            print("Blocked URL without hostname")
            return False
        try:
            infos = socket.getaddrinfo(parsed.hostname, None, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            print(f"Failed to resolve hostname {parsed.hostname}: {e}")
            return False
        if not infos:
            print(f"No addresses returned for hostname {parsed.hostname}")
            return False
        seen = set()
        for info in infos:
            ip_str = info[4][0]
            if ip_str in seen:
                continue
            seen.add(ip_str)
            try:
                ip_obj = ipaddress.ip_address(ip_str)
            except ValueError:
                print(f"Invalid IP from DNS: {ip_str!r}")
                return False
            for blocked_range in Config.BLOCKED_IP_RANGES:
                if ip_obj in blocked_range:
                    print(f"Blocked access to private/internal IP: {ip_str} ({parsed.hostname})")
                    return False
        return True
    except Exception as e:
        print(f"URL validation error: {e}")
        return False


def get_game_link(game):
    """Construct the store link for a game."""
    loc = epic_config.STORE_PATH_LOCALE
    product_slug = game.get('productSlug')
    if product_slug:
        return f"https://store.epicgames.com/{loc}/p/{product_slug}"
    mappings = game.get('catalogNs', {}).get('mappings', [])
    if mappings:
        page_slug = mappings[0].get('pageSlug')
        if page_slug:
            return f"https://store.epicgames.com/{loc}/p/{page_slug}"
    offer_mappings = game.get('offerMappings') or []
    if offer_mappings:
        page_slug = offer_mappings[0].get('pageSlug')
        if page_slug:
            return f"https://store.epicgames.com/{loc}/p/{page_slug}"
    url_slug = game.get('urlSlug')
    if url_slug:
        return f"https://store.epicgames.com/{loc}/p/{url_slug}"
    return None


def extract_game_metadata(game):
    """Extract additional metadata fields from the API game object."""
    catalog_ns = game.get('catalogNs') or {}
    mappings = catalog_ns.get('mappings') or []
    mapping_slug = mappings[0].get('pageSlug') if mappings else None
    seller = game.get('seller') or {}
    return {
        'description': (game.get('description') or '').strip() or None,
        'developer': (game.get('developerDisplayName') or '').strip() or None,
        'publisher': (game.get('publisherDisplayName') or '').strip() or None,
        'seller_name': (seller.get('name') or '').strip() or None,
        'sandbox_id': game.get('namespace') or game.get('sandboxId'),
        'mapping_slug': mapping_slug,
        'product_slug': game.get('productSlug'),
        'url_slug': game.get('urlSlug'),
    }


def get_game_image_url(game):
    """Get the best image URL for a game."""
    key_images = game.get('keyImages', [])
    for image_type in ['OfferImageWide', 'OfferImageTall', 'Thumbnail', 'featuredMedia']:
        for image in key_images:
            if image.get('type') == image_type:
                return image.get('url')
    if key_images:
        return key_images[0].get('url')
    return None


def get_game_price(game):
    """Extract original price (cents) and currency code from game API data."""
    price_data = game.get('price', {})
    total_price = price_data.get('totalPrice', {}) if price_data else {}
    original_price_cents = total_price.get('originalPrice')
    currency_code = total_price.get('currencyCode', 'USD')
    return original_price_cents, currency_code


def epic_free_discount_percentage(offer):
    """Return discountPercentage as int, or None if missing/malformed."""
    if not isinstance(offer, dict):
        return None
    ds = offer.get('discountSetting')
    if not isinstance(ds, dict):
        return None
    pct = ds.get('discountPercentage')
    if pct is None:
        return None
    try:
        return int(pct)
    except (TypeError, ValueError):
        return None


def parse_offer_iso_dates(offer, game_title='?'):
    """Return (start, end) as timezone-aware datetimes, or (None, None) if invalid."""
    if not isinstance(offer, dict):
        return None, None
    start_raw = offer.get('startDate')
    end_raw = offer.get('endDate')
    if not start_raw or not end_raw:
        return None, None
    try:
        start = datetime.fromisoformat(str(start_raw).replace('Z', '+00:00'))
        end = datetime.fromisoformat(str(end_raw).replace('Z', '+00:00'))
        return start, end
    except (ValueError, TypeError) as e:
        print(f"Skipping offer with bad dates for {game_title!r}: {e}")
        return None, None


@lru_cache(maxsize=128)
def format_date(iso_date):
    """Format ISO date to human-readable format. Cached for performance."""
    try:
        dt = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
        return dt.strftime('%b %d at %I:%M %p')
    except (ValueError, AttributeError, TypeError) as e:
        print(f"Date formatting failed for '{iso_date}': {e}")
        return str(iso_date)


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
        print(f"Failed to save API hash: {e}")
