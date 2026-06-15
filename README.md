# Epic Games Free Games History Tracker

A complete system for tracking Epic Games Store free games since 2018, featuring automated scraping, SQLite database storage, and a beautiful static website with search and filtering.

**Live Website**: https://evenwebb.github.io/epic-free-games-scraper/

---

## Features

### 🎮 **Complete History**
- **600+ PC games tracked** from December 2018 to present (count grows with each scrape)
- SQLite database with full promotion history
- Automatic image fetching and storage
- Optimized JPG images under `output/images/`
- No manual updates needed for day-to-day runs

### 🌐 **Beautiful Static Website**
- Timeline view of all free games by year and month
- Full-text search (SQLite FTS5) with tag filtering
- Individual game detail pages with metadata and promotion history
- Dark mode with automatic OS preference detection
- PWA support (installable, offline-capable)
- RSS and iCalendar feeds for new game notifications
- Statistics dashboard with charts
- Lazy loading for fast performance
- Countdown timers for current free games
- Responsive design (mobile-friendly)

### 🤖 **Automated Scraping**
- Uses official Epic Games API (no HTML scraping) — extracts all available fields
- Modular design: `scraper.py`, `models.py`, `db_manager.py`, `image_utils.py`, `epic_config.py`
- Runs automatically daily at 4pm UK time via GitHub Actions
- Downloads high-quality game images with ETag caching
- Updates database and website automatically
- Skips heavy work when the API payload is unchanged (hash check)

### 📊 **Data Storage**
- SQLite database for efficient querying
- JSON export for the static site (`website/data/`)
- Game images on disk, referenced from the database
- Historical data since 2018
- Price data captured in **GBP** (API uses GB storefront settings in `epic_config.py`)

---

## How It Works

1. **Scraper** (`scrape_epic_games.py`) fetches free games from Epic API (GB region for GBP pricing)
2. **Database** (`output/epic_games.db`) stores games, promotions, metadata, prices, and images
3. **Website Generator** (`generate_website.py`) creates static HTML/CSS/JS site with all data
4. **GitHub Actions** automatically runs the process daily at 4pm UK time and deploys to GitHub Pages

---

## Quick Start

### Local Development

```bash
# Clone the repository
git clone https://github.com/evenwebb/epic-free-games-scraper.git
cd epic-free-games-scraper

# Install dependencies
pip install -r requirements.txt

# Run the scraper
python3 scrape_epic_games.py

# Generate the website
python3 generate_website.py

# View the website locally
cd website
python3 -m http.server 8000
# Open http://localhost:8000
```

### First Time Setup

If you're starting fresh without the database:

```bash
# Run scraper (creates database and tables automatically; downloads images)
python3 scrape_epic_games.py

# Generate website
python3 generate_website.py
```

The scraper retries missing or invalid images on later runs when those games still appear in the Epic free-games API.

---

## GitHub Pages Deployment

The website is automatically deployed to GitHub Pages via GitHub Actions.

### Setup Instructions

1. **Enable GitHub Pages**:
   - Go to repository Settings → Pages
   - Source: "GitHub Actions"

2. **Commit and Push**:
   ```bash
   git add .
   git commit -m "Initial setup"
   git push origin main
   ```

3. **GitHub Actions will automatically**:
   - Check daily (4pm UK) whether the Epic API payload changed
   - When it changed: run the scraper, then regenerate the site and deploy if the database or images changed
   - Commit database / image / `.api_hash` updates back to the repository when applicable

4. **View your site** at: `https://[username].github.io/epic-free-games-scraper/`

### Manual Trigger

You can manually trigger the workflow:
- Go to Actions tab → "Scrape Epic Games and Deploy to GitHub Pages"
- Click "Run workflow"

---

## Scripts

### `scrape_epic_games.py`
Fetches current and upcoming free games from the Epic API (URL and locale live in `epic_config.py`), downloads images, and updates the database.

```bash
python3 scrape_epic_games.py
```

### `generate_website.py`
Generates the complete static website from the database.

```bash
python3 generate_website.py
```

When copying images into `website/images/`, the script warns if the database references files that are missing under `output/images/`. In **GitHub Actions** (`CI=true`), it **fails the job** unless you set `GENERATE_WEBSITE_ALLOW_MISSING_IMAGES=1` (emergency override only). Locally you can force failure with `GENERATE_WEBSITE_FAIL_ON_MISSING_IMAGES=1`.

### `scripts/api_hash_check.py`
Used by Actions to compare the live free-games API JSON to `output/.api_hash` (stdlib + `urllib` only; no `pip install` in that step). Not normally run by hand.

---

## Configuration

API endpoint and storefront locale are centralized in **`epic_config.py`** (`FREE_GAMES_PROMOTIONS_URL`, `STORE_PATH_LOCALE`) so the scraper and hash check always stay in sync.

---

## Database Schema

### Tables

- **games**: Game information (name, link, rating, image, platform)
- **promotions**: Free game promotion periods (start, end, status)
- **scrape_history**: Audit trail of scraper runs
- **statistics_cache**: Pre-computed statistics for website

### Queries

```python
from db_manager import DatabaseManager

db = DatabaseManager()

# Get current free games
current = db.get_current_games(platform='PC')

# Get all games chronologically
all_games = db.get_all_games_chronological()

# Get statistics
stats = db.get_statistics()
```

---

## Website Features

### Timeline View
- All games organised by year and month
- Lazy loading (50 games at a time)
- Game images with fallback placeholders
- Links to Epic Store pages

### Search & Filters
- Search by game name (powered by SQLite FTS5 full-text search)
- Filter by year (2018–present)
- Filter by tags (Action, Adventure, RPG, Strategy, etc.)
- Sort by: Newest, Oldest, A-Z, Rating

### Detail Pages
- Individual game pages with full metadata
- Price history and promotion timeline
- Publisher, developer, platform, and rating info
- Related games and tag-based navigation

### RSS & Calendar Feeds
- RSS feed of recently added free games
- iCalendar (.ics) feed for promotion start/end dates
- Subscribe to get notified when new free games are available

### PWA & Mobile
- Progressive Web App (installable to home screen)
- Offline support with service worker caching
- Dark mode with automatic OS preference detection

### Statistics Dashboard
- Total games tracked
- Total value of free games
- Average game price
- Current year value
- Games per year chart
- Average games per week
- Current free games count

### Current Free Games
- Hero section at top
- Countdown timers
- Direct "Get It Free" links
- High-quality images

---

## GitHub Actions

### `scrape-and-deploy.yml` (scrape + Pages)

Runs automatically with:

**Schedule**: Daily around 4pm UK time (**15:00** and **16:00 UTC** cron lines cover **BST** vs **GMT**).

**Triggers**:
- Schedule (cron)
- Manual **workflow_dispatch**
- Push to **main** (ignored for paths that only touch `**.md` / `LICENSE` / `.gitattributes`)

**Flow** (single job, optimized):
1. Shallow checkout
2. Run **`scripts/api_hash_check.py`** — if the API payload matches `output/.api_hash`, the workflow skips installing Python dependencies, **`scrape_epic_games.py`**, and all commit/deploy steps for that run (fast path).
3. If the API changed: set up **Python 3.11**, install dependencies, run **`scrape_epic_games.py`**
4. If `output/epic_games.db` or `output/images/` changed: run **`generate_website.py`**, commit outputs, configure Pages, upload artifact, deploy (with one retry on deploy failure)
5. If only the hash metadata needs updating: commit **`output/.api_hash`** when needed

**Concurrency**: New runs cancel older in-progress **pages** workflow runs.

### `ci.yml` (tests + site build smoke test)

On push / PR to **main** (same `paths-ignore` as above for Markdown-only changes):

1. Shallow checkout, Python **3.11**, pip cache
2. `pip install -r requirements.txt`
3. **`pytest`**
4. **`generate_website.py`** against the committed DB
5. Assert `website/index.html` and `website/data/games.json` exist

**Concurrency**: New commits cancel superseded CI runs on the same branch / PR.

---

## Requirements

- **Python 3.11+** (matches CI)
- See **`requirements.txt`**: `requests`, `Pillow`, `pytest`

```bash
pip install -r requirements.txt
```

## License

This project is licensed under the **GPL-3.0 License** - see the [LICENSE](LICENSE) file for details.

## Credits

- Data sourced from [Epic Games Store API](https://store.epicgames.com)
- Historical data from community tracking
- Not affiliated with Epic Games
