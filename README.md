# Epic Games Free Games History Tracker

A complete system for tracking Epic Games Store free games since 2018, featuring automated scraping, SQLite database storage, and a beautiful static website with search and filtering.

**Live Website**: https://evenwebb.github.io/epic-free-games-scraper/

---

## Features

### 🎮 **Complete History**
- **584+ PC games tracked** from December 2018 to present
- SQLite database with full promotion history
- Automatic image fetching and storage
- All games have optimized images
- No manual updates needed

### 🌐 **Beautiful Static Website**
- Timeline view of all free games by year and month
- Search by game name
- Filter by year and sort options
- Statistics dashboard with charts
- Lazy loading for fast performance
- Countdown timers for current free games
- Responsive design (mobile-friendly)

### 🤖 **Automated Scraping**
- Uses official Epic Games API (no web scraping)
- Runs automatically every 6 hours via GitHub Actions
- Downloads high-quality game images
- Updates database and website automatically
- Pushover notifications (optional)

### 📊 **Data Storage**
- SQLite database for efficient querying
- JSON export for compatibility
- 584+ optimized game images
- Historical data since 2018
- Price tracking with regional support (GBP/USD)

---

## How It Works

1. **Scraper** (`scrape_epic_games.py`) fetches free games from Epic API (GB region for GBP pricing)
2. **Database** (`output/epic_games.db`) stores games, promotions, metadata, prices, and images
3. **Website Generator** (`generate_website.py`) creates static HTML/CSS/JS site with all data
4. **GitHub Actions** automatically runs the process every 6 hours and deploys to GitHub Pages

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
# Run scraper (creates database and tables automatically)
python3 scrape_epic_games.py

# Fetch images for games missing them (optional; requires STEAMGRIDDB_API_KEY)
python3 fetch_missing_images.py

# Generate website
python3 generate_website.py
```

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
   - Run the scraper every 6 hours
   - Update the database
   - Generate the website
   - Deploy to GitHub Pages
   - Commit database updates back to the repository

4. **View your site** at: `https://[username].github.io/epic-free-games-scraper/`

### Manual Trigger

You can manually trigger the workflow:
- Go to Actions tab → "Scrape Epic Games and Deploy to GitHub Pages"
- Click "Run workflow"

---

## Scripts

### `scrape_epic_games.py`
Fetches current and upcoming free games from the Epic API, downloads images, and updates the database.

```bash
python3 scrape_epic_games.py
```

### `fetch_missing_images.py`
Downloads images for games that don't have them (uses SteamGridDB when `STEAMGRIDDB_API_KEY` is set).

```bash
export STEAMGRIDDB_API_KEY="your_key"
python3 fetch_missing_images.py

# Re-fetch specific games (e.g. wrong aspect ratio)
python3 fetch_missing_images.py --re-fetch <epic_id> [epic_id ...]
```

### `generate_website.py`
Generates the complete static website from the database.

```bash
python3 generate_website.py
```

---

## Configuration

### Pushover Notifications (Optional)

Create `settings.json`:

```json
{
  "pushover": {
    "enabled": true,
    "user_key": "your_user_key",
    "app_token": "your_app_token",
    "notify_always": false
  }
}
```

- `enabled`: Turn notifications on/off
- `notify_always`: Notify for all games (true) or only new games (false)

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
- Search by game name
- Filter by year (2018-2025)
- Sort by: Newest, Oldest, A-Z, Rating

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

The workflow (`.github/workflows/scrape-and-deploy.yml`) runs automatically:

**Schedule**: Every 6 hours (0:00, 6:00, 12:00, 18:00 UTC)

**Triggers**:
- Scheduled (cron)
- Manual dispatch
- Push to main branch

**Steps**:
1. Check out repository
2. Set up Python 3.11
3. Install dependencies
4. Run scraper (creates database automatically on first run)
5. Generate website
6. Commit database updates
7. Deploy to GitHub Pages

---

## Requirements

- Python 3.9+
- `requests` library (only dependency!)

```bash
pip install -r requirements.txt
```

## License

This project is licensed under the **GPL-3.0 License** - see the [LICENSE](LICENSE) file for details.

## Credits

- Data sourced from [Epic Games Store API](https://store.epicgames.com)
- Historical data from community tracking
- Not affiliated with Epic Games
