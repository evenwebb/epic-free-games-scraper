# Image Storage Architecture

## Overview
To avoid storing duplicate images in the repository, we use a single-source approach where images are only committed in `output/images/` and dynamically copied to `website/images/` during website generation.

## Directory Structure

```
epic-free-games-scraper/
├── output/
│   └── images/              ← SOURCE: Committed to Git (449 images, 54MB)
└── website/
    └── images/              ← GENERATED: NOT committed (created from output/images/)
```

## How It Works

### 1. **Image Downloads**
All scripts download images to `output/images/`:
- `scrape_epic_games.py` - Main scraper (current & upcoming games)
- `fetch_historical_images.py` - Historical games with Google fallback
- `fetch_missing_images_epic_only.py` - Epic API only

### 2. **Website Generation**
When you run `generate_website.py`:
- Copies all images from `output/images/` → `website/images/`
- Updates `website/data/games.json` with image paths
- Generates static HTML

### 3. **Git Tracking**
- ✅ `output/images/` - **Committed to git**
- ❌ `website/images/` - **Ignored** (in .gitignore)

### 4. **GitHub Actions Deployment**
The workflow automatically:
1. Checks out repo (gets `output/images/`)
2. Runs `generate_website.py` (creates `website/images/`)
3. Deploys `website/` folder to GitHub Pages

## Benefits

### ✅ Storage Savings
- **Before**: 180MB (54MB in output + 126MB in website)
- **After**: 54MB (only output/ committed)
- **Savings**: 126MB (~70% reduction)

### ✅ Simplified Workflow
- Only maintain images in one location
- No manual syncing needed
- Automatic cleanup of old images

### ✅ Faster Git Operations
- Smaller repo size
- Faster clones/pulls
- Less merge conflicts

## Local Development

### First Time Setup
```bash
# Clone the repo
git clone https://github.com/yourusername/epic-free-games-scraper.git
cd epic-free-games-scraper

# Generate website (creates website/images/)
python3 generate_website.py

# View website
open website/index.html
```

### Daily Workflow
```bash
# Run scraper (saves to output/images/)
python3 scrape_epic_games.py

# Regenerate website (copies to website/images/)
python3 generate_website.py

# Commit changes (only output/images/ is tracked)
git add output/
git commit -m "Add new images"
git push
```

## Important Notes

1. **Never commit `website/images/`** - It's auto-generated
2. **Always run `generate_website.py`** before testing locally
3. **GitHub Actions handles it automatically** in production
4. **All image formats** are automatically converted to JPG

## Troubleshooting

### Missing Images on Website
```bash
# Regenerate website/images/ from output/images/
python3 generate_website.py
```

### Images in Git Status
```bash
# If website/images/ shows up in git:
git rm -r --cached website/images/
git add .gitignore
git commit -m "Remove website/images from tracking"
```

### Clean Old Images
```bash
# Remove old/unused images in website/
rm -rf website/images/
python3 generate_website.py
```

## Image Format

All images are:
- **Format**: JPEG
- **Quality**: 85%
- **Resolution**: 1280x720 (optimized for web)
- **Avg Size**: ~120KB per image
- **Mode**: RGB (transparency converted to white background)
