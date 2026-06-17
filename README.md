# Epic Games Free Games History Tracker

A complete system for tracking Epic Games Store free games since 2018, featuring automated scraping, SQLite database storage, and a beautiful static website with search and filtering.

**Live Website**: [evenwebb.github.io/epic-free-games-scraper](https://evenwebb.github.io/epic-free-games-scraper/)

[![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Games Tracked](https://img.shields.io/badge/games-623-brightgreen.svg)](https://evenwebb.github.io/epic-free-games-scraper/)

---

## Quick Navigation

- [Features](#features)
- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [Scripts](#scripts)
- [GitHub Pages Deployment](#github-pages-deployment)
- [Configuration](#configuration)
- [Database Schema](#database-schema)
- [Website Features](#website-features)
- [GitHub Actions](#github-actions)
- [Known Limitations](#known-limitations)
- [Requirements](#requirements)
- [License](#license)
- [Credits](#credits)

---

## Features

### Data Collection
- **623 PC games tracked** from December 2018 to present
- **688 total promotions** including repeat free periods
- SQLite database with full promotion history and FTS5 full-text search
- Automatic image fetching with ETag caching — JPG and WebP output
- Price data captured in GBP (via GB storefront locale)
- No manual updates needed for day-to-day runs

### Static Website
- Timeline view of all free games by year and month with lazy loading
- Full-text search (SQLite FTS5) with year, offer type, and sort filters
- Individual game detail pages with metadata, price history, and promotion timeline
- Hero section showing current free games with countdown timers
- Coming Soon section for upcoming free games
- Statistics dashboard with Chart.js visualizations
- Dark mode toggle with automatic OS preference detection and persisted state
- PWA support (installable, offline-capable via service worker)
- RSS and iCalendar feeds for new game notifications
- Responsive design (mobile and tablet friendly)
- Timeline cards show game value/price alongside ratings

### Automated Scraping
- Uses official Epic Games API (no HTML scraping)
- Modular design: `scrape_epic_games.py`, `epic_client.py`, `image_processor.py`, `db_manager.py`, `epic_config.py`
- Runs automatically daily at 4pm UK time via GitHub Actions
- API hash check skips heavy work when the free games payload hasn't changed
- Database and images committed back to the repo automatically

---

## How It Works

1. **Scraper** (`scrape_epic_games.py`) fetches free games from Epic API (GB region for GBP pricing)
2. **Image Processor** (`image_processor.py`) downloads and optimizes game images as both JPG and WebP
3. **Database** (`output/epic_games.db`) stores games, promotions, metadata, prices, and image references
4. **Website Generator** (`generate_website.py`) creates the static HTML/CSS/JS site from the database
5. **GitHub Actions** automatically runs the process daily and deploys to GitHub Pages

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

## Scripts

### `scrape_epic_games.py`
Main entry point. Fetches current and upcoming free games from the Epic API (URL and locale live in `epic_config.py`), downloads images via `image_processor.py`, and updates the database via `db_manager.py`.

```bash
python3 scrape_epic_games.py
```

### `generate_website.py`
Generates the complete static website from the database. Exports `website/data/games.json`, generates individual game detail pages, index page with current/upcoming hero sections, statistics, RSS/ICS feeds, and syncs images to `website/images/`.

```bash
python3 generate_website.py
```

> **Note**: When copying images, the script warns if the database references files missing from `output/images/`. In **GitHub Actions** (`CI=true`), it **fails the job** unless you set `GENERATE_WEBSITE_ALLOW_MISSING_IMAGES=1` (emergency override only). Locally you can force failure with `GENERATE_WEBSITE_FAIL_ON_MISSING_IMAGES=1`.

### `scripts/api_hash_check.py`
Used by Actions to compare the live free-games API JSON to `output/.api_hash` (stdlib + `urllib` only; no `pip install` required in that step). Not normally run by hand.

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
   - When changed: run the scraper, then regenerate the site and deploy if the database or images changed
   - Commit database / image / `.api_hash` updates back to the repository

4. **View your site** at: `https://[username].github.io/epic-free-games-scraper/`

### Manual Trigger

You can manually trigger the workflow:
- Go to Actions tab → "Scrape Epic Games and Deploy to GitHub Pages"
- Click "Run workflow"

> **Tip**: Delete `output/.api_hash` and push to force the scraper to run on the next workflow execution, even if the API payload hasn't changed.

---

## Configuration

API endpoint and storefront locale are centralized in **`epic_config.py`**:

- `FREE_GAMES_PROMOTIONS_URL` — Epic Games free games promotions API endpoint
- `STORE_PATH_LOCALE` — Storefront locale (currently `en-GB` for GBP pricing)

Both the scraper and hash check read these values so they always stay in sync.

---

## Database Schema

### Tables

| Table | Description |
|-------|-------------|
| `games` | Game information (name, link, rating, image, platform, price, offer type, tags, categories) |
| `promotions` | Free game promotion periods (start date, end date, status) |
| `scrape_history` | Audit trail of scraper runs |
| `statistics_cache` | Pre-computed statistics for the website |

### Query Examples

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

### Current Free Games
- Hero section at the top of the page
- Countdown timers showing time remaining
- Direct "Get It Free" links to the Epic Games Store
- High-quality game images with seller and description info

### Coming Soon
- Dedicated section for upcoming free games
- Shows availability date and promotion duration
- Links to add games to wishlist before they go free

### Timeline View
- All games organised by year and month
- Infinite scroll with "Load More" (50 games at a time)
- Game cards with images, ratings, and value/price display
- Links to Epic Store pages and individual detail pages

### Search & Filters
- Search by game name (powered by SQLite FTS5 full-text search)
- Filter by offer type (Full Games, Add-ons, DLC, Editions, Bundles)
- Filter by year (2018–present)
- Sort by: Newest First, Oldest First, A-Z, Highest Rated

### Game Detail Pages
- Individual game pages with full metadata
- Price history and promotion timeline
- Publisher/seller, platform, rating, tags, and categories
- Full game description

### Statistics Dashboard
- Total games tracked, current free count, total promotions
- Games per week average, current year total value
- Chart.js bar chart: games per year

### RSS & Calendar Feeds
- RSS feed of recently added free games
- iCalendar (.ics) feed for promotion start/end dates
- Subscribe to get notified when new free games are available

### PWA & Mobile
- Progressive Web App (installable to home screen)
- Offline support with service worker caching
- Responsive design for mobile, tablet, and desktop

---

## GitHub Actions

### `scrape-and-deploy.yml`

Runs automatically with:

**Schedule**: Daily around 4pm UK time (**15:00** and **16:00 UTC** cron lines cover BST vs GMT).

**Triggers**:
- Schedule (cron)
- Manual **workflow_dispatch**
- Push to **main** (ignores paths that only touch `**.md` / `LICENSE` / `.gitattributes`)

**Flow** (single job, optimized):
1. Shallow checkout
2. Run **`scripts/api_hash_check.py`** — if the API payload matches `output/.api_hash`, the workflow skips installing Python dependencies, running `scrape_epic_games.py`, and all commit/deploy steps (fast path)
3. If the API changed: set up **Python 3.11**, install dependencies, run **`scrape_epic_games.py`**
4. If `output/epic_games.db` or `output/images/` changed: run **`generate_website.py`**, commit outputs, configure Pages, upload artifact, deploy (with one retry on deploy failure)
5. If only the hash metadata needs updating: commit **`output/.api_hash`**

**Concurrency**: New runs cancel older in-progress **pages** workflow runs.

### `ci.yml`

On push / PR to **main** (same `paths-ignore` for Markdown-only changes):

1. Shallow checkout, Python **3.11**, pip cache
2. `pip install -r requirements.txt`
3. **`pytest`**
4. **`generate_website.py`** against the committed DB
5. Assert `website/index.html` and `website/data/games.json` exist

**Concurrency**: New commits cancel superseded CI runs on the same branch / PR.

---

## Known Limitations

- **Game ratings unavailable since November 2025**: Epic removed ratings from the public free games API. 65 of 623 games have no rating. No publicly accessible Epic API currently provides this data. IGDB or Steam APIs could be potential alternative sources.
- **Price data limited to current promotions**: The scraper only captures prices while games are in the free games API (typically 1-2 weeks). Historical prices for older promotions may not be available.

---

## Requirements

- **Python 3.11+** (matches CI)
- See **`requirements.txt`**: `requests`, `Pillow`, `pytest`

```bash
pip install -r requirements.txt
```

---

## License

This project is licensed under the **GPL-3.0 License** — see the [LICENSE](LICENSE) file for details.

---

## Credits

- Data sourced from [Epic Games Store](https://store.epicgames.com) API
- Historical data from community tracking
- Not affiliated with Epic Games

---

*If you find this project useful, consider starring the repo on [GitHub](https://github.com/evenwebb/epic-free-games-scraper)!*
