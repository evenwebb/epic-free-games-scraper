#!/usr/bin/env python3
"""
Migrate historical data from epic_free_games.json to SQLite database.
This script imports all games from 2018-present including PC, iOS, and Android games.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from db_manager import DatabaseManager

def parse_date(date_string):
    """Parse date string to ISO format timestamp"""
    try:
        # Assume date is in YYYY-MM-DD format
        dt = datetime.strptime(date_string, '%Y-%m-%d')
        # Set time to 16:00 UTC (typical Epic Games free game time)
        dt = dt.replace(hour=16, minute=0, second=0, tzinfo=timezone.utc)
        return dt.isoformat()
    except:
        print(f"Warning: Could not parse date: {date_string}")
        return None

def estimate_end_date(start_date_str):
    """Estimate end date by adding 7 days to start date"""
    try:
        dt = datetime.fromisoformat(start_date_str)
        # Epic Games typically offers games for 1 week
        end_dt = dt + timedelta(days=7)
        return end_dt.isoformat()
    except:
        return None

def determine_promotion_status(start_date_str, end_date_str):
    """Determine if a promotion is current, upcoming, or expired"""
    now = datetime.now(timezone.utc)
    try:
        start = datetime.fromisoformat(start_date_str)
        end = datetime.fromisoformat(end_date_str)

        if start <= now <= end:
            return 'current'
        elif start > now:
            return 'upcoming'
        else:
            return 'expired'
    except:
        # Default to expired for historical games
        return 'expired'

def extract_id_from_link(link):
    """Extract game ID from Epic Store link"""
    if not link:
        return None
    # Link format: https://store.epicgames.com/en-US/p/game-slug
    parts = link.strip('/').split('/')
    if len(parts) > 0:
        return parts[-1]
    return None

def migrate_historical_data(json_file='epic_free_games.json', dry_run=False):
    """Migrate data from JSON to database"""

    if not os.path.exists(json_file):
        print(f"Error: {json_file} not found!")
        return

    print(f"Loading historical data from {json_file}...")

    with open(json_file, 'r', encoding='utf-8') as f:
        games = json.load(f)

    print(f"Found {len(games)} games in historical data")

    if dry_run:
        print("DRY RUN MODE - No data will be written to database")
        # Show sample of first 5 games
        for i, game in enumerate(games[:5]):
            print(f"\nSample Game {i+1}:")
            print(f"  Title: {game.get('gameTitle')}")
            print(f"  Epic ID: {game.get('epicId')}")
            print(f"  Platform: {game.get('platform', 'PC (default)')}")
            print(f"  Free Date: {game.get('freeDate')}")
            print(f"  Rating: {game.get('epicRating')}")
            print(f"  Link: {game.get('epicStoreLink')}")
        return

    db = DatabaseManager()
    imported_count = 0
    skipped_count = 0
    error_count = 0

    print("\nImporting games to database...")

    for i, game in enumerate(games):
        try:
            # Extract game data
            epic_id = game.get('epicId')
            name = game.get('gameTitle')
            link = game.get('epicStoreLink')
            free_date = game.get('freeDate')
            platform = game.get('platform', 'PC')  # Default to PC if not specified
            epic_rating = game.get('epicRating')
            sandbox_id = game.get('sandboxId')
            mapping_slug = game.get('mappingSlug')
            product_slug = game.get('productSlug')
            url_slug = game.get('urlSlug')

            # Validate required fields
            if not all([name, link, free_date]):
                print(f"Skipping game {i+1}: Missing required fields (name, link, or date)")
                skipped_count += 1
                continue

            # Generate epic_id for mobile games if missing
            if not epic_id or epic_id.strip() == '':
                # For mobile games, use mapping_slug or generate from link
                if mapping_slug:
                    epic_id = f"{platform.lower()}-{mapping_slug}"
                else:
                    # Extract from link or use name-based ID
                    link_parts = link.strip('/').split('/')
                    epic_id = f"{platform.lower()}-{link_parts[-1]}" if link_parts else f"{platform.lower()}-{name.lower().replace(' ', '-')}"
                print(f"  Generated ID for {name} ({platform}): {epic_id}")

            # Skip mobile games - PC only
            platform_upper = platform.upper()
            if platform_upper in ['IOS', 'ANDROID', 'MOBILE']:
                print(f"  Skipping mobile game: {name} ({platform})")
                skipped_count += 1
                continue

            # Normalize platform to PC
            platform = 'PC'

            # Parse dates
            start_date = parse_date(free_date)
            if not start_date:
                print(f"Skipping {name}: Invalid date format")
                skipped_count += 1
                continue

            end_date = estimate_end_date(start_date)
            if not end_date:
                print(f"Skipping {name}: Could not estimate end date")
                skipped_count += 1
                continue

            # Determine promotion status
            status = determine_promotion_status(start_date, end_date)

            # Insert or update game
            game_id = db.insert_or_update_game(
                epic_id=epic_id,
                name=name,
                link=link,
                platform=platform,
                epic_rating=epic_rating,
                image_filename=None,  # Historical games don't have images yet
                sandbox_id=sandbox_id,
                mapping_slug=mapping_slug,
                product_slug=product_slug,
                url_slug=url_slug
            )

            # Insert promotion
            # Historical games were already free, so mark as notified
            db.insert_promotion(
                game_id=game_id,
                start_date=start_date,
                end_date=end_date,
                status=status,
                platform=platform,
                notified=True  # Historical data, already past
            )

            imported_count += 1

            # Progress indicator
            if (i + 1) % 100 == 0:
                print(f"  Processed {i + 1}/{len(games)} games...")

        except Exception as e:
            print(f"Error importing game {i+1} ({game.get('gameTitle', 'Unknown')}): {e}")
            error_count += 1
            continue

    print(f"\nMigration complete!")
    print(f"  Successfully imported: {imported_count} games")
    print(f"  Skipped: {skipped_count} games")
    print(f"  Errors: {error_count} games")

    # Update statistics
    print("\nUpdating statistics cache...")
    db.update_statistics_cache()

    # Show summary
    stats = db.get_statistics()
    platform_counts = db.get_platform_counts()

    print(f"\nDatabase Summary:")
    print(f"  Total games: {stats.get('total_games', 0)}")
    print(f"  Total promotions: {stats.get('total_promotions', 0)}")
    print(f"  Platform breakdown:")
    for platform, count in platform_counts.items():
        print(f"    {platform}: {count} games")

    if stats.get('first_game_date'):
        print(f"  First free game: {stats.get('first_game_date')}")

    years = db.get_games_by_year()
    if years:
        print(f"  Games by year:")
        for year, count in years.items():
            print(f"    {year}: {count} games")

if __name__ == '__main__':
    import sys

    # Check for dry-run flag
    dry_run = '--dry-run' in sys.argv or '-d' in sys.argv

    if dry_run:
        print("=" * 60)
        print("DRY RUN MODE - Showing sample data only")
        print("=" * 60)

    migrate_historical_data(dry_run=dry_run)

    if dry_run:
        print("\nTo perform actual migration, run:")
        print("  python migrate_historical_data.py")
