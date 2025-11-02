#!/usr/bin/env python3
"""
Cleanup orphaned and missing images.
- Removes image files on disk that aren't in database
- Clears database entries pointing to non-existent files
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

def remove_orphaned_images(orphaned_images):
    """Delete orphaned image files from disk"""
    if not orphaned_images:
        return 0

    image_dir = Path('output/images')
    removed = 0

    for filename in orphaned_images:
        filepath = image_dir / filename
        if filepath.exists():
            try:
                filepath.unlink()
                print(f"  🗑️  Removed: {filename}")
                removed += 1
            except Exception as e:
                print(f"  ⚠️  Failed to remove {filename}: {e}")

    return removed

def clear_missing_image_entries(missing_games):
    """Clear image_filename for games with missing files"""
    if not missing_games:
        return 0

    db = DatabaseManager()
    cleared = 0

    with db.get_connection() as conn:
        cursor = conn.cursor()
        for game in missing_games:
            cursor.execute("""
                UPDATE games
                SET image_filename = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (game['id'],))

            print(f"  🧹 Cleared: {game['name']} (missing: {game['image_filename']})")
            cleared += 1

    return cleared

def main(auto_cleanup=False):
    print("=" * 70)
    print("Image Cleanup Tool")
    print("=" * 70)

    # Get data
    images_on_disk = get_images_on_disk()
    db_images = get_images_in_database()

    print(f"\n📁 Images on disk: {len(images_on_disk)}")
    print(f"💾 Images in database: {len(db_images)}")

    # Find issues
    print("\n" + "-" * 70)
    print("Finding orphaned images (on disk but not in database)...")
    print("-" * 70)

    orphaned = find_orphaned_images()
    if orphaned:
        print(f"⚠️  Found {len(orphaned)} orphaned images:")
        for img in sorted(orphaned):
            print(f"  - {img}")
    else:
        print("✓ No orphaned images found")

    print("\n" + "-" * 70)
    print("Finding missing images (in database but not on disk)...")
    print("-" * 70)

    missing = find_missing_images()
    if missing:
        print(f"⚠️  Found {len(missing)} missing images:")
        for game in missing:
            print(f"  - {game['name']}: {game['image_filename']}")
    else:
        print("✓ No missing images found")

    # Cleanup
    if orphaned or missing:
        print("\n" + "=" * 70)
        print("Cleanup Actions")
        print("=" * 70)

        if not auto_cleanup:
            response = input(f"\nCleanup {len(orphaned)} orphaned files and {len(missing)} database entries? (y/n): ")
            if response.lower() != 'y':
                print("Cleanup cancelled")
                return

        # Remove orphaned files
        if orphaned:
            print(f"\nRemoving {len(orphaned)} orphaned image files...")
            removed = remove_orphaned_images(orphaned)
            print(f"✓ Removed {removed} files")

        # Clear missing entries
        if missing:
            print(f"\nClearing {len(missing)} database entries...")
            cleared = clear_missing_image_entries(missing)
            print(f"✓ Cleared {cleared} entries")

        # Final verification
        print("\n" + "=" * 70)
        print("Verification After Cleanup")
        print("=" * 70)

        images_on_disk_after = get_images_on_disk()
        db_images_after = get_images_in_database()

        print(f"📁 Images on disk: {len(images_on_disk_after)}")
        print(f"💾 Images in database: {len(db_images_after)}")

        orphaned_after = find_orphaned_images()
        missing_after = find_missing_images()

        if len(orphaned_after) == 0 and len(missing_after) == 0:
            print("\n✓ All images are now synchronized!")
        else:
            print(f"\n⚠️  Still have {len(orphaned_after)} orphaned and {len(missing_after)} missing")

    else:
        print("\n✓ No cleanup needed - everything is synchronized!")

    print("=" * 70)

if __name__ == '__main__':
    import sys

    # Check for --clean flag
    auto_cleanup = '--clean' in sys.argv

    if auto_cleanup:
        print("Auto-cleanup mode enabled\n")

    main(auto_cleanup=auto_cleanup)
