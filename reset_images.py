#!/usr/bin/env python3
"""
Reset all images - delete all image files and clear database references.
Use this to start fresh when images have been incorrectly matched.
"""

import os
from pathlib import Path
from db_manager import DatabaseManager

def count_images_on_disk():
    """Count all image files in output/images/"""
    image_dir = Path('output/images')
    if not image_dir.exists():
        return 0

    count = 0
    for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
        count += len(list(image_dir.glob(ext)))

    return count

def delete_all_images():
    """Delete all image files from output/images/"""
    image_dir = Path('output/images')
    if not image_dir.exists():
        print("  No images directory found")
        return 0

    deleted = 0
    for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
        for img_file in image_dir.glob(ext):
            try:
                img_file.unlink()
                deleted += 1
            except Exception as e:
                print(f"  ⚠️  Failed to delete {img_file.name}: {e}")

    return deleted

def clear_all_database_references():
    """Clear all image_filename fields in database"""
    db = DatabaseManager()

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Count how many will be cleared
        cursor.execute("""
            SELECT COUNT(*) FROM games
            WHERE image_filename IS NOT NULL AND image_filename != ''
        """)
        count = cursor.fetchone()[0]

        # Clear all image references
        cursor.execute("""
            UPDATE games
            SET image_filename = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE image_filename IS NOT NULL AND image_filename != ''
        """)

    return count

def main(auto_confirm=False):
    print("=" * 70)
    print("IMAGE RESET TOOL - NUCLEAR OPTION")
    print("=" * 70)
    print("\n⚠️  WARNING: This will DELETE ALL images and clear database!")
    print()

    # Count what will be deleted
    image_count = count_images_on_disk()

    db = DatabaseManager()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM games
            WHERE image_filename IS NOT NULL AND image_filename != ''
        """)
        db_count = cursor.fetchone()[0]

    print(f"📁 Images on disk: {image_count}")
    print(f"💾 Database records with images: {db_count}")
    print()

    if image_count == 0 and db_count == 0:
        print("✓ No images to delete - already clean!")
        return

    # Confirm
    if not auto_confirm:
        print("This will:")
        print(f"  1. Delete {image_count} image files from output/images/")
        print(f"  2. Clear {db_count} database image references")
        print()
        response = input("Are you ABSOLUTELY SURE you want to continue? (type 'yes' to confirm): ")

        if response.lower() != 'yes':
            print("\n❌ Reset cancelled")
            return

    # Execute deletion
    print("\n" + "=" * 70)
    print("Executing Reset...")
    print("=" * 70)

    # Delete files
    print(f"\n🗑️  Deleting {image_count} image files...")
    deleted_files = delete_all_images()
    print(f"✓ Deleted {deleted_files} files")

    # Clear database
    print(f"\n🧹 Clearing {db_count} database references...")
    cleared_db = clear_all_database_references()
    print(f"✓ Cleared {cleared_db} database records")

    # Verify
    print("\n" + "=" * 70)
    print("Verification")
    print("=" * 70)

    remaining_images = count_images_on_disk()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM games
            WHERE image_filename IS NOT NULL AND image_filename != ''
        """)
        remaining_db = cursor.fetchone()[0]

    print(f"📁 Images remaining on disk: {remaining_images}")
    print(f"💾 Database records with images: {remaining_db}")

    if remaining_images == 0 and remaining_db == 0:
        print("\n✅ RESET COMPLETE - All images deleted and database cleared!")
        print("\nYou can now run fetch_historical_images.py to re-fetch with improved logic.")
    else:
        print(f"\n⚠️  Warning: {remaining_images} images and {remaining_db} database records still remain")

    print("=" * 70)

if __name__ == '__main__':
    import sys

    # Check for --yes flag to skip confirmation
    auto_confirm = '--yes' in sys.argv

    if auto_confirm:
        print("Auto-confirm mode enabled\n")

    main(auto_confirm=auto_confirm)
