"""Image download, validation, conversion, and parallel processing."""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

import requests
from PIL import Image

from epic_client import Config, validate_url


def is_valid_cached_image(file_path):
    """Check if a cached image file exists and is valid."""
    if not os.path.exists(file_path):
        return False
    try:
        file_size = os.path.getsize(file_path)
        if file_size < 1024:
            return False
        with Image.open(file_path) as img:
            if img.format not in ('JPEG', 'JPG'):
                return False
            if img.width < 50 or img.height < 50:
                return False
            return True
    except (OSError, IOError, Image.UnidentifiedImageError):
        return False


def download_and_convert_image(image_url, output_path, session=None):
    """Download an image and convert to optimized JPG."""
    if is_valid_cached_image(output_path):
        return True
    if not validate_url(image_url):
        raise ValueError(f"Invalid or unsafe URL: {image_url}")

    http_client = session if session else requests

    try:
        with http_client.get(
            image_url,
            timeout=Config.IMAGE_DOWNLOAD_TIMEOUT,
            stream=True,
            allow_redirects=True,
        ) as img_response:
            img_response.raise_for_status()
            final_url = img_response.url
            if not validate_url(final_url):
                raise ValueError(f"Redirect led to unsafe URL: {final_url}")

            content_length = img_response.headers.get('Content-Length')
            if content_length and int(content_length) > Config.MAX_IMAGE_SIZE:
                raise ValueError(
                    f"Image too large: {content_length} bytes (max {Config.MAX_IMAGE_SIZE})"
                )

            content = BytesIO()
            downloaded_bytes = 0
            for chunk in img_response.iter_content(chunk_size=Config.DOWNLOAD_CHUNK_SIZE):
                if chunk:
                    downloaded_bytes += len(chunk)
                    if downloaded_bytes > Config.MAX_IMAGE_SIZE:
                        raise ValueError(f"Download exceeded {Config.MAX_IMAGE_SIZE} bytes")
                    content.write(chunk)

            content.seek(0)
            img = Image.open(content)

            if img.width > Config.MAX_IMAGE_DIMENSION or img.height > Config.MAX_IMAGE_DIMENSION:
                raise ValueError(
                    f"Image dimensions too large: {img.width}x{img.height} "
                    f"(max {Config.MAX_IMAGE_DIMENSION})"
                )

            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            img.save(output_path, 'JPEG', quality=Config.IMAGE_QUALITY, optimize=Config.IMAGE_OPTIMIZE)
        return True

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to download image from {image_url}: {e}") from e
    except (OSError, IOError) as e:
        raise RuntimeError(f"Failed to process/save image to {output_path}: {e}") from e


def download_image_task(image_url, image_path, game_title, session, retries=2):
    """Task wrapper for parallel image downloading with retry logic."""
    last_error = None
    for attempt in range(retries + 1):
        try:
            download_and_convert_image(image_url, image_path, session=session)
            if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
                return {'success': True, 'game': game_title, 'path': image_path}
            last_error = f"File was not created: {image_path}"
        except Exception as e:
            last_error = str(e)
            if attempt < retries:
                continue
        break
    return {'success': False, 'game': game_title, 'error': last_error, 'path': image_path}


def _download_task_display_name(task):
    """Human-readable name for an image download task."""
    name = (
        task.get('game')
        or task.get('new_name')
        or task.get('old_name')
        or task.get('epic_id')
    )
    if name:
        return str(name)
    path = task.get('path')
    return os.path.basename(path) if path else 'unknown'


def run_parallel_image_downloads(download_tasks, session):
    """Run download_image_task for each task; return (successful_paths_set, failures_list)."""
    successful_downloads = set()
    failed_downloads = []
    if not download_tasks:
        return successful_downloads, failed_downloads
    print(f"Downloading {len(download_tasks)} images in parallel...")
    with ThreadPoolExecutor(max_workers=Config.MAX_DOWNLOAD_WORKERS) as executor:
        future_to_task = {
            executor.submit(
                download_image_task,
                task['url'],
                task['path'],
                _download_task_display_name(task),
                session,
            ): task
            for task in download_tasks
        }
        for future in as_completed(future_to_task):
            result = future.result()
            if result['success']:
                print(f"Downloaded: {result['game']}")
                successful_downloads.add(result['path'])
            else:
                print(f"Failed: {result['game']} - {result['error']}")
                failed_downloads.append(result)
    if failed_downloads:
        print(
            f"\n"
            f"{len(failed_downloads)} image downloads failed. "
            f"These will be retried on the next scrape run."
        )
    return successful_downloads, failed_downloads


def apply_successful_image_updates_to_db(db, successful_downloads, mystery_updates):
    """Persist image (and optional mystery reveal name) after successful downloads."""
    if not successful_downloads:
        return
    print("Updating existing games with successfully downloaded images...")
    with db.get_connection() as conn:
        cursor = conn.cursor()
        updated_count = 0
        mystery_revealed_count = 0
        for image_path in successful_downloads:
            image_filename = os.path.basename(image_path)
            epic_id = os.path.splitext(image_filename)[0]
            mystery_info = mystery_updates.get(epic_id)
            if mystery_info and mystery_info.get('update_name'):
                cursor.execute("""
                    UPDATE games
                    SET name = ?, image_filename = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE epic_id = ? AND platform = 'PC'
                """, (mystery_info['new_name'], image_filename, epic_id))
                if cursor.rowcount > 0:
                    mystery_revealed_count += 1
                    print(f"  Revealed: {mystery_info['old_name']} -> {mystery_info['new_name']}")
            else:
                cursor.execute("""
                    UPDATE games
                    SET image_filename = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE epic_id = ? AND platform = 'PC'
                    AND (image_filename IS NULL OR image_filename = '')
                """, (image_filename, epic_id))
                if cursor.rowcount > 0:
                    updated_count += 1
            if mystery_info and not mystery_info.get('update_name'):
                cursor.execute("""
                    UPDATE games
                    SET image_filename = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE epic_id = ? AND platform = 'PC'
                """, (image_filename, epic_id))
        conn.commit()
        if updated_count > 0:
            print(f"Updated image_filename for {updated_count} existing games")
        if mystery_revealed_count > 0:
            print(f"Revealed and updated {mystery_revealed_count} mystery games")


def clear_orphaned_game_image_filenames(db):
    """Clear DB image_filename when the file is missing or fails validation."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, epic_id, name, image_filename FROM games "
            "WHERE image_filename IS NOT NULL AND image_filename != ''"
        )
        for row in cursor.fetchall():
            img_path = os.path.join(Config.IMAGES_DIR, row['image_filename'])
            if not is_valid_cached_image(img_path):
                cursor.execute(
                    "UPDATE games SET image_filename = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (row['id'],)
                )
                if cursor.rowcount > 0:
                    print(f"  Cleared orphaned image ref: {row['name']}")
