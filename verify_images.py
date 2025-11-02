#!/usr/bin/env python3
"""
Verify that all images on disk are correctly recorded in the database.
Checks for:
1. Images on disk but not in database
2. Images in database but not on disk
3. Games that could use existing images
"""

import os
from pathlib import Path
from db_manager import DatabaseManager

def get_images_on_disk():
    """Get all image files in output/images/"""
    image_dir = Path('output/images')
    if not image_dir.exists():
        return set()

    images = set()
    for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
        images.update([f.name for f in image_dir.glob(ext)])

    return images

def get_images_in_database():
    """Get all image filenames from database"""
    db = DatabaseManager()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, epic_id, name, image_filename
            FROM games
            WHERE image_filename IS NOT NULL AND image_filename != ''
        """)

        results = cursor.fetchall()

    return [dict(row) for row in results]

def find_orphaned_images():
    """Find images on disk that aren't in database"""
    images_on_disk = get_images_on_disk()
    db_images = get_images_in_database()
    db_filenames = {game['image_filename'] for game in db_images}

    orphaned = images_on_disk - db_filenames
    return orphaned

def find_missing_images():
    """Find database entries pointing to non-existent files"""
    images_on_disk = get_images_on_disk()
    db_images = get_images_in_database()

    missing = []
    for game in db_images:
        if game['image_filename'] not in images_on_disk:
            missing.append(game)

    return missing

def find_fixable_games():
    """Find games without image_filename but have matching image on disk"""
    db = DatabaseManager()
    images_on_disk = get_images_on_disk()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, epic_id, name, image_filename
            FROM games
            WHERE platform = 'PC' AND (image_filename IS NULL OR image_filename = '')
        """)

        games_without_images = [dict(row) for row in cursor.fetchall()]

    fixable = []
    for game in games_without_images:
        epic_id = game['epic_id']
        # Check for any matching image file (jpg, png, webp)
        for ext in ['jpg', 'jpeg', 'png', 'webp']:
            filename = f"{epic_id}.{ext}"
            if filename in images_on_disk:
                fixable.append({
                    'game': game,
                    'found_image': filename
                })
                break

    return fixable

def fix_database_entries(fixable_games, auto_fix=False):
    """Update database entries for games with orphaned images"""
    if not fixable_games:
        return 0

    if not auto_fix:
        print("\nFound games that can be fixed:")
        for item in fixable_games:
            print(f"  - {item['game']['name']}: {item['found_image']}")

        response = input(f"\nFix {len(fixable_games)} games in database? (y/n): ")
        if response.lower() != 'y':
            return 0

    db = DatabaseManager()
    fixed = 0

    with db.get_connection() as conn:
        cursor = conn.cursor()
        for item in fixable_games:
            game = item['game']
            image_filename = item['found_image']

            cursor.execute("""
                UPDATE games
                SET image_filename = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (image_filename, game['id']))

            print(f"  ✓ Fixed: {game['name']} -> {image_filename}")
            fixed += 1

    return fixed

def main(auto_fix=False):
    print("=" * 70)
    print("Image Verification Tool")
    print("=" * 70)

    # Get data
    images_on_disk = get_images_on_disk()
    db_images = get_images_in_database()

    print(f"\n📁 Images on disk: {len(images_on_disk)}")
    print(f"💾 Images in database: {len(db_images)}")

    # Check for orphaned images
    print("\n" + "-" * 70)
    print("Checking for orphaned images (on disk but not in database)...")
    print("-" * 70)

    orphaned = find_orphaned_images()
    if orphaned:
        print(f"⚠️  Found {len(orphaned)} orphaned images:")
        for img in sorted(orphaned)[:10]:
            print(f"  - {img}")
        if len(orphaned) > 10:
            print(f"  ... and {len(orphaned) - 10} more")
    else:
        print("✓ No orphaned images found")

    # Check for missing images
    print("\n" + "-" * 70)
    print("Checking for missing images (in database but not on disk)...")
    print("-" * 70)

    missing = find_missing_images()
    if missing:
        print(f"⚠️  Found {len(missing)} missing images:")
        for game in missing[:10]:
            print(f"  - {game['name']}: {game['image_filename']}")
        if len(missing) > 10:
            print(f"  ... and {len(missing) - 10} more")
    else:
        print("✓ No missing images found")

    # Check for fixable games
    print("\n" + "-" * 70)
    print("Checking for fixable games (images exist but not recorded)...")
    print("-" * 70)

    fixable = find_fixable_games()
    if fixable:
        print(f"🔧 Found {len(fixable)} games that can be auto-fixed:")
        for item in fixable[:10]:
            print(f"  - {item['game']['name']}: {item['found_image']}")
        if len(fixable) > 10:
            print(f"  ... and {len(fixable) - 10} more")

        # Offer to fix
        fixed = fix_database_entries(fixable, auto_fix=auto_fix)
        if fixed > 0:
            print(f"\n✓ Fixed {fixed} database entries")
    else:
        print("✓ No fixable games found")

    # Summary
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"  Images on disk: {len(images_on_disk)}")
    print(f"  Database records: {len(db_images)}")
    print(f"  Orphaned images: {len(orphaned)}")
    print(f"  Missing images: {len(missing)}")
    print(f"  Fixed games: {len(fixable) if fixable else 0}")

    if len(orphaned) == 0 and len(missing) == 0:
        print("\n✓ All images are correctly synchronized!")
    else:
        print("\n⚠️  Some inconsistencies found - review above")

    print("=" * 70)

if __name__ == '__main__':
    import sys

    # Check for --fix flag
    auto_fix = '--fix' in sys.argv

    if auto_fix:
        print("Auto-fix mode enabled\n")

    main(auto_fix=auto_fix)
