"""Epic Games Store free games scraper — main orchestrator."""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

import epic_config

from db_manager import DatabaseManager
from epic_client import (
    Config,
    compute_api_hash,
    epic_free_discount_percentage,
    extract_game_metadata,
    format_date,
    get_game_image_url,
    get_game_link,
    get_game_price,
    load_previous_api_hash,
    parse_offer_iso_dates,
    sanitize_filename,
    save_api_hash,
)
from image_processor import (
    apply_successful_image_updates_to_db,
    clear_orphaned_game_image_filenames,
    is_valid_cached_image,
    run_parallel_image_downloads,
)


def write_scrape_run_summary(payload):
    """Write JSON summary for ops/CI; append markdown to GITHUB_STEP_SUMMARY when set."""
    try:
        os.makedirs(Config.OUTPUT_DIR, exist_ok=True)
        path = Config.SCRAPE_SUMMARY_FILE
        payload = {**payload, 'finished_at': datetime.now(timezone.utc).isoformat()}
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, default=str)
    except OSError as e:
        print(f"Failed to write scrape summary: {e}")

    summary_file = os.environ.get('GITHUB_STEP_SUMMARY')
    if not summary_file:
        return
    lines = [
        '### Scrape run',
        f"- **success**: {payload.get('success')}",
        f"- **duration_s**: {payload.get('duration_seconds')}",
    ]
    if payload.get('early_exit_api_unchanged'):
        lines.append('- **early exit**: API payload unchanged (hash match)')
    h = payload.get('api_hash_sha256')
    if h:
        lines.append(f"- **api_hash**: `{h[:16]}…`")
    if payload.get('catalog_element_count') is not None:
        lines.append(f"- **catalog elements**: {payload['catalog_element_count']}")
    for key in ('games_found', 'new_games', 'current_free', 'upcoming'):
        if key in payload and payload[key] is not None:
            lines.append(f"- **{key}**: {payload[key]}")
    if payload.get('image_download_tasks') is not None:
        lines.append(f"- **image tasks**: {payload['image_download_tasks']}")
    fails = payload.get('image_download_failures') or []
    if fails:
        lines.append(f"- **image failures**: {len(fails)}")
        for item in fails[:5]:
            lines.append(f"  - {item.get('game')}: {item.get('error', '')[:120]}")
        if len(fails) > 5:
            lines.append(f"  - _…and {len(fails) - 5} more_")
    if payload.get('error'):
        lines.append(f"- **error**: {payload['error'][:500]}")
    try:
        with open(summary_file, 'a', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
    except OSError as e:
        print(f"Failed to append step summary: {e}")


def collect_upcoming_promo_image_filenames(games):
    """Basenames used by upcoming free promotions for legacy cleanup."""
    filenames = set()
    for game in games:
        if not game.get('promotions'):
            continue
        game_title = game['title']
        game_link = get_game_link(game)
        if not game_link:
            continue
        upcoming_offers = game['promotions'].get('upcomingPromotionalOffers', [])
        if not upcoming_offers:
            continue
        for offer_group in upcoming_offers:
            for offer in offer_group.get('promotionalOffers', []):
                if epic_free_discount_percentage(offer) != 0:
                    continue
                _, end = parse_offer_iso_dates(offer, game_title)
                if end is None:
                    continue
                upcoming_game_id = sanitize_filename(game.get('id', game_link.split('/')[-1]))
                image_filename = f"{upcoming_game_id}.jpg"
                if image_filename:
                    filenames.add(image_filename)
    return filenames


def collect_retry_and_mystery_download_tasks(all_games, games):
    """Find games needing image downloads: missing images and mystery game reveals."""
    print("Checking for existing games missing images...")
    existing_games_missing_images = {}
    for g in all_games:
        if g.get('platform') != 'PC':
            continue
        if not g.get('image_filename'):
            existing_games_missing_images[g['epic_id']] = g
        else:
            img_path = os.path.join(Config.IMAGES_DIR, g['image_filename'])
            if not is_valid_cached_image(img_path):
                existing_games_missing_images[g['epic_id']] = g

    mystery_games_to_update = [g for g in all_games
                               if g.get('platform') == 'PC' and 'mystery' in g['name'].lower()]

    api_games_by_id = {game.get('id'): game for game in games if game.get('id')}
    retry_download_tasks = []
    mystery_update_tasks = []

    for epic_id, db_game in existing_games_missing_images.items():
        api_game = api_games_by_id.get(epic_id)
        if api_game:
            image_url = get_game_image_url(api_game)
            if image_url:
                image_filename = f"{sanitize_filename(epic_id)}.jpg"
                image_path = os.path.join(Config.IMAGES_DIR, image_filename)
                if not is_valid_cached_image(image_path):
                    retry_download_tasks.append({
                        'url': image_url, 'path': image_path,
                        'game': db_game['name'], 'type': 'retry',
                    })

    for db_game in mystery_games_to_update:
        epic_id = db_game['epic_id']
        api_game = api_games_by_id.get(epic_id)
        if api_game:
            api_name = api_game.get('title', '')
            db_name = db_game['name']
            is_revealed = (
                'mystery' not in api_name.lower()
                and api_name.lower() != db_name.lower()
            )
            image_url = get_game_image_url(api_game)
            if image_url:
                image_filename = f"{sanitize_filename(epic_id)}.jpg"
                image_path = os.path.join(Config.IMAGES_DIR, image_filename)
                mystery_update_tasks.append({
                    'url': image_url, 'path': image_path,
                    'epic_id': epic_id, 'old_name': db_name,
                    'new_name': api_name if is_revealed else db_name,
                    'update_name': is_revealed,
                    'game': api_name if is_revealed else db_name,
                    'type': 'mystery_update',
                })

    download_tasks = []
    mystery_updates = {}
    if retry_download_tasks:
        print(f"Found {len(retry_download_tasks)} existing games to retry image downloads")
        download_tasks.extend(retry_download_tasks)
    if mystery_update_tasks:
        print(f"Found {len(mystery_update_tasks)} mystery games to update")
        download_tasks.extend([
            {k: v for k, v in task.items() if k != 'update_name'}
            for task in mystery_update_tasks
        ])
        mystery_updates = {task['epic_id']: task for task in mystery_update_tasks}
    return download_tasks, mystery_updates


def cleanup_legacy_next_game_files(kept_basenames):
    """Remove legacy next-game*.jpg files no longer tied to upcoming promos."""
    kept = set(kept_basenames)
    for filename in os.listdir(Config.IMAGES_DIR):
        if (filename.startswith("next-game")
                and filename.endswith(".jpg")
                and filename not in kept):
            try:
                filepath = os.path.join(Config.IMAGES_DIR, filename)
                os.remove(filepath)
                print(f"Removed unused file: {filename}")
            except OSError as e:
                print(f"Failed to remove {filename}: {e}")


def scrape_epic_free_games():
    db = DatabaseManager()
    os.makedirs(Config.IMAGES_DIR, exist_ok=True)

    all_games = db.get_all_games_chronological()
    existing_games_dict = {game['link']: game for game in all_games}

    new_games = []
    current_games = []
    next_games = []

    session = requests.Session()
    run_started = time.monotonic()

    try:
        db.update_promotion_status()

        api_url = epic_config.FREE_GAMES_PROMOTIONS_URL

        print("Fetching free games from Epic Games API...")
        response = session.get(api_url, timeout=Config.API_REQUEST_TIMEOUT)
        response.raise_for_status()

        api_data = response.json()

        try:
            games = api_data['data']['Catalog']['searchStore']['elements']
        except (KeyError, TypeError) as e:
            raise ValueError(f"Unexpected API response structure: {e}") from e
        if not isinstance(games, list):
            raise ValueError("API did not return a list of games")

        current_hash = compute_api_hash(api_data)
        previous_hash = load_previous_api_hash()

        if current_hash == previous_hash and previous_hash is not None:
            print("API response unchanged — skipping full catalog update; running image maintenance")
            maintenance_tasks, mystery_updates = collect_retry_and_mystery_download_tasks(
                all_games, games
            )
            successful_downloads, failed_downloads = run_parallel_image_downloads(
                maintenance_tasks, session
            )
            apply_successful_image_updates_to_db(db, successful_downloads, mystery_updates)
            clear_orphaned_game_image_filenames(db)
            cleanup_legacy_next_game_files(collect_upcoming_promo_image_filenames(games))

            save_api_hash(current_hash)
            db.record_scrape_run(
                games_found=len(games), new_games=0, current=0, upcoming=0, success=True
            )
            db.update_statistics_cache()
            write_scrape_run_summary({
                'success': True,
                'early_exit_api_unchanged': True,
                'duration_seconds': round(time.monotonic() - run_started, 3),
                'api_hash_sha256': current_hash,
                'catalog_element_count': len(games),
                'games_found': len(games),
                'new_games': 0, 'current_free': 0, 'upcoming': 0,
                'image_download_tasks': len(maintenance_tasks),
                'image_download_failures': [
                    {'game': r['game'], 'error': r.get('error', '')}
                    for r in failed_downloads
                ],
            })
            return

        print("API response changed - processing updates...")
        now = datetime.now(timezone.utc)

        games_to_insert = []
        promotions_to_insert = []
        download_tasks = []

        # First pass: upcoming games to capture prices before they become free
        for game in games:
            if not game.get('promotions'):
                continue
            game_title = game['title']
            game_link = get_game_link(game)
            if not game_link:
                print(f"Skipping {game_title}: no valid link found")
                continue

            upcoming_offers = game['promotions'].get('upcomingPromotionalOffers', [])
            if upcoming_offers and len(upcoming_offers) > 0:
                for offer_group in upcoming_offers:
                    for offer in offer_group.get('promotionalOffers', []):
                        if epic_free_discount_percentage(offer) != 0:
                            continue
                        _, _end = parse_offer_iso_dates(offer, game_title)
                        if _end is None:
                            continue
                        image_url = get_game_image_url(game)
                        availability = (
                            f"{format_date(offer['startDate'])} - "
                            f"{format_date(offer['endDate'])}"
                        )
                        original_price_cents, currency_code = get_game_price(game)
                        upcoming_game_id = sanitize_filename(
                            game.get('id', game_link.split('/')[-1])
                        )
                        image_filename = f"{upcoming_game_id}.jpg"
                        image_path = os.path.join(Config.IMAGES_DIR, image_filename)

                        if image_url and not is_valid_cached_image(image_path):
                            download_tasks.append({
                                'url': image_url, 'path': image_path,
                                'game': game_title, 'type': 'upcoming',
                            })

                        meta = extract_game_metadata(game)
                        games_to_insert.append({
                            'epic_id': upcoming_game_id,
                            'name': game_title,
                            'link': game_link,
                            'platform': 'PC',
                            'image_filename': image_filename,
                            'original_price_cents': original_price_cents,
                            'currency_code': currency_code,
                            **meta,
                        })
                        promotions_to_insert.append({
                            'epic_id': upcoming_game_id, 'platform': 'PC',
                            'start_date': offer['startDate'],
                            'end_date': offer['endDate'],
                            'status': 'upcoming',
                        })
                        next_games.append({
                            'Name': game_title, 'Link': game_link,
                            'Image': image_path, 'Availability': availability,
                        })

        # Second pass: currently free games
        for game in games:
            if not game.get('promotions'):
                continue
            game_title = game['title']
            game_link = get_game_link(game)
            if not game_link:
                continue

            promo_offers = game['promotions'].get('promotionalOffers', [])
            if promo_offers and len(promo_offers) > 0:
                for offer_group in promo_offers:
                    for offer in offer_group.get('promotionalOffers', []):
                        start, end = parse_offer_iso_dates(offer, game_title)
                        if start is None:
                            continue
                        if not (start <= now <= end and epic_free_discount_percentage(offer) == 0):
                            continue
                        image_url = get_game_image_url(game)
                        game_id = sanitize_filename(game.get('id', game_link.split('/')[-1]))
                        date_period = f"Free Now - {format_date(offer['endDate'])}"

                        original_price_cents, currency_code = get_game_price(game)
                        if original_price_cents == 0:
                            original_price_cents = None
                            currency_code = None

                        image_filename = None
                        image_path = None
                        if image_url:
                            image_filename = f"{game_id}.jpg"
                            image_path = os.path.join(Config.IMAGES_DIR, image_filename)
                            if not is_valid_cached_image(image_path):
                                download_tasks.append({
                                    'url': image_url, 'path': image_path,
                                    'game': game_title, 'type': 'current',
                                })

                        meta = extract_game_metadata(game)
                        games_to_insert.append({
                            'epic_id': game_id,
                            'name': game_title,
                            'link': game_link,
                            'platform': 'PC',
                            'image_filename': image_filename,
                            'original_price_cents': original_price_cents,
                            'currency_code': currency_code,
                            **meta,
                        })
                        promotions_to_insert.append({
                            'epic_id': game_id, 'platform': 'PC',
                            'start_date': offer['startDate'],
                            'end_date': offer['endDate'],
                            'status': 'current',
                        })

                        if game_link not in existing_games_dict:
                            new_games.append(game_title)

                        current_games.append({
                            'Name': game_title, 'Link': game_link,
                            'Image': image_path, 'Availability': date_period,
                        })

        existing_next_game_images = collect_upcoming_promo_image_filenames(games)
        extra_tasks, mystery_updates = collect_retry_and_mystery_download_tasks(all_games, games)
        download_tasks.extend(extra_tasks)
        successful_downloads, failed_downloads = run_parallel_image_downloads(
            download_tasks, session
        )

        # Only set image_filename if the file actually exists
        for game_data in games_to_insert:
            if game_data.get('image_filename'):
                image_path = os.path.join(Config.IMAGES_DIR, game_data['image_filename'])
                file_exists = is_valid_cached_image(image_path) or image_path in successful_downloads
                if not file_exists:
                    game_data['image_filename'] = None

        print(f"Batch inserting {len(games_to_insert)} games...")
        game_id_map = db.batch_insert_or_update_games(games_to_insert)

        for promo in promotions_to_insert:
            epic_id = promo.pop('epic_id')
            platform = promo['platform']
            promo['game_id'] = game_id_map.get((epic_id, platform))
            if not promo['game_id']:
                print(f"Warning: Could not find game_id for {epic_id}")

        print(f"Batch inserting {len(promotions_to_insert)} promotions...")
        db.batch_insert_promotions(promotions_to_insert)

        apply_successful_image_updates_to_db(db, successful_downloads, mystery_updates)
        clear_orphaned_game_image_filenames(db)
        cleanup_legacy_next_game_files(existing_next_game_images)

        print(f"Data scraped successfully. Found {len(new_games)} new games.")
        save_api_hash(current_hash)

        db.record_scrape_run(
            games_found=len(games), new_games=len(new_games),
            current=len(current_games), upcoming=len(next_games), success=True,
        )
        db.update_statistics_cache()

        write_scrape_run_summary({
            'success': True,
            'early_exit_api_unchanged': False,
            'duration_seconds': round(time.monotonic() - run_started, 3),
            'api_hash_sha256': current_hash,
            'catalog_element_count': len(games),
            'games_found': len(games),
            'new_games': len(new_games),
            'current_free': len(current_games),
            'upcoming': len(next_games),
            'image_download_tasks': len(download_tasks),
            'image_download_failures': [
                {'game': r['game'], 'error': r.get('error', '')}
                for r in failed_downloads
            ],
        })

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
        try:
            db.record_scrape_run(
                games_found=0, new_games=0, current=0, upcoming=0,
                success=False, error=str(e),
            )
        except Exception as db_error:
            print(f"Failed to record error in database: {db_error}")
        write_scrape_run_summary({
            'success': False,
            'duration_seconds': round(time.monotonic() - run_started, 3),
            'error': str(e),
            'image_download_failures': [],
        })
        sys.exit(1)
    finally:
        session.close()


if __name__ == '__main__':
    scrape_epic_free_games()
