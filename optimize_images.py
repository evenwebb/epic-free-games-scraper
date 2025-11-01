#!/usr/bin/env python3
"""
Optimize and resize images for web display.
Compresses JPG images and resizes them to appropriate dimensions for the website.
"""

import os
from pathlib import Path
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("ERROR: Pillow library not found. Install with: pip install Pillow")
    exit(1)

# Target dimensions for hero/banner images
MAX_WIDTH = 1920
MAX_HEIGHT = 1080
JPEG_QUALITY = 85  # Good balance between quality and file size

def should_optimize_image(image_path):
    """Check if image needs optimization based on size and dimensions."""
    try:
        # Check file size (if > 500KB, likely needs optimization)
        file_size = os.path.getsize(image_path) / 1024  # KB

        with Image.open(image_path) as img:
            width, height = img.size

            # Needs optimization if:
            # - File is larger than 500KB
            # - Width is larger than MAX_WIDTH
            # - Height is larger than MAX_HEIGHT
            needs_optimization = (
                file_size > 500 or
                width > MAX_WIDTH or
                height > MAX_HEIGHT
            )

            return needs_optimization, width, height, file_size
    except Exception as e:
        print(f"    Error checking image: {e}")
        return False, 0, 0, 0

def optimize_image(image_path):
    """Resize and compress image for web display."""
    try:
        with Image.open(image_path) as img:
            # Convert to RGB if necessary (handles RGBA, P modes)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Get current dimensions
            width, height = img.size
            original_size = os.path.getsize(image_path) / 1024  # KB

            # Calculate new dimensions maintaining aspect ratio
            if width > MAX_WIDTH or height > MAX_HEIGHT:
                # Calculate scaling factor
                width_ratio = MAX_WIDTH / width
                height_ratio = MAX_HEIGHT / height
                scale_factor = min(width_ratio, height_ratio)

                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)

                # Resize using high-quality Lanczos resampling
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                print(f"    Resized: {width}x{height} → {new_width}x{new_height}")
            else:
                print(f"    Size OK: {width}x{height}")

            # Save with optimization
            img.save(image_path, 'JPEG', quality=JPEG_QUALITY, optimize=True)

            new_size = os.path.getsize(image_path) / 1024  # KB
            saved = original_size - new_size
            saved_pct = (saved / original_size * 100) if original_size > 0 else 0

            print(f"    Compressed: {original_size:.1f}KB → {new_size:.1f}KB (saved {saved:.1f}KB, {saved_pct:.1f}%)")

            return True

    except Exception as e:
        print(f"    Error optimizing image: {e}")
        return False

def optimize_images_in_directory(directory):
    """Optimize all JPG images in a directory."""
    print(f"\nProcessing images in: {directory}")
    print("=" * 60)

    image_dir = Path(directory)
    if not image_dir.exists():
        print(f"Directory not found: {directory}")
        return

    # Find all JPG images
    jpg_files = list(image_dir.glob("*.jpg")) + list(image_dir.glob("*.jpeg"))

    if not jpg_files:
        print("No JPG images found")
        return

    print(f"Found {len(jpg_files)} JPG images\n")

    optimized = 0
    skipped = 0
    failed = 0

    for i, img_path in enumerate(sorted(jpg_files), 1):
        print(f"[{i}/{len(jpg_files)}] {img_path.name}")

        needs_opt, width, height, file_size = should_optimize_image(img_path)

        if not needs_opt:
            print(f"    Already optimized: {width}x{height}, {file_size:.1f}KB - skipping")
            skipped += 1
            continue

        print(f"    Current: {width}x{height}, {file_size:.1f}KB")

        if optimize_image(img_path):
            optimized += 1
        else:
            failed += 1

    print("\n" + "=" * 60)
    print(f"Summary for {directory}:")
    print(f"  Optimized: {optimized} images")
    print(f"  Skipped: {skipped} images (already optimized)")
    print(f"  Failed: {failed} images")
    print("=" * 60)

def main():
    """Main function to optimize images in both directories."""
    print("=" * 60)
    print("Epic Games Image Optimizer")
    print("=" * 60)

    if not PIL_AVAILABLE:
        return

    # Optimize images in output/images/
    optimize_images_in_directory("output/images")

    # Optimize images in website/images/
    optimize_images_in_directory("website/images")

    print("\n✓ Image optimization complete!")

if __name__ == '__main__':
    main()
