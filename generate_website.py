#!/usr/bin/env python3
"""
Generate static website from the Epic Games free games database.
Creates a complete static site with HTML, CSS, JS, and data files.
"""

import html
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from db_manager import DatabaseManager
from epic_client import resolve_tag_names

_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, '').strip().lower() in ('1', 'true', 'yes', 'on')

def ensure_directory(path):
    """Create directory if it doesn't exist"""
    os.makedirs(path, exist_ok=True)

def copy_images(db):
    """
    Incrementally sync game images to website directory.

    Performance: Only copies images referenced in the database (skips orphaned files).
    Only copies new/changed files instead of re-copying everything.
    """
    source = 'output/images'
    dest = 'website/images'

    if not os.path.exists(source):
        print("Warning: No images directory found")
        ensure_directory(dest)
        return

    ensure_directory(dest)

    # Only copy images that are referenced by games in the database
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT DISTINCT image_filename FROM games WHERE image_filename IS NOT NULL AND image_filename != ''"
        )
        needed_images = {row[0] for row in cursor.fetchall()}

    dest_files = set(os.listdir(dest)) if os.path.exists(dest) else set()
    copied = 0
    skipped = 0
    removed = 0

    missing_sources = []
    for filename in sorted(needed_images):
        lower = filename.lower()
        if not lower.endswith(_IMAGE_EXTENSIONS):
            continue
        source_path = os.path.join(source, filename)
        if not os.path.exists(source_path):
            missing_sources.append(filename)

    # Copy new or modified images (only those referenced in DB)
    for filename in needed_images:
        if not filename.lower().endswith(_IMAGE_EXTENSIONS):
            continue
        source_path = os.path.join(source, filename)
        if not os.path.exists(source_path):
            continue
        dest_path = os.path.join(dest, filename)

        # Check if file needs copying (new or modified)
        needs_copy = True
        if os.path.exists(dest_path):
            source_mtime = os.path.getmtime(source_path)
            dest_mtime = os.path.getmtime(dest_path)
            source_size = os.path.getsize(source_path)
            dest_size = os.path.getsize(dest_path)
            if source_size == dest_size and dest_mtime >= source_mtime:
                needs_copy = False
                skipped += 1

        if needs_copy:
            shutil.copy2(source_path, dest_path)
            copied += 1

    # Remove images from dest that are no longer needed
    for filename in dest_files:
        if filename.lower().endswith(_IMAGE_EXTENSIONS) and filename not in needed_images:
            dest_path = os.path.join(dest, filename)
            os.remove(dest_path)
            removed += 1

    print(f"Images sync: {copied} copied, {skipped} skipped, {removed} removed ({len(needed_images)} total)")

    if missing_sources:
        n = len(missing_sources)
        preview = missing_sources[:15]
        suffix = f" (+{n - len(preview)} more)" if n > len(preview) else ""
        print(
            f"⚠️  {n} image file(s) referenced in the database are missing under {source!r}: "
            f"{', '.join(preview)}{suffix}",
            file=sys.stderr,
        )
        in_ci = os.environ.get('CI') == 'true'
        force_fail = _env_truthy('GENERATE_WEBSITE_FAIL_ON_MISSING_IMAGES')
        allow_missing = _env_truthy('GENERATE_WEBSITE_ALLOW_MISSING_IMAGES')
        if force_fail or (in_ci and not allow_missing):
            print(
                "Error: Refusing to publish with missing images. "
                "Restore files under output/images, or re-run the scraper. "
                "To override in CI only if you accept broken thumbnails: "
                "set GENERATE_WEBSITE_ALLOW_MISSING_IMAGES=1.",
                file=sys.stderr,
            )
            raise SystemExit(1)

def export_data_json(db):
    """Export database data to JSON for website consumption"""
    print("Exporting data from database...")

    # Get statistics
    stats = db.get_statistics()
    platform_counts = db.get_platform_counts()
    games_by_year = db.get_games_by_year()

    # Get games for all platforms
    current_games_pc = db.get_current_games(platform='PC')
    upcoming_games_pc = db.get_upcoming_games(platform='PC')
    all_games_pc = db.get_all_games_chronological(platform='PC')
    all_games_ios = db.get_all_games_chronological(platform='iOS')
    all_games_android = db.get_all_games_chronological(platform='Android')

    # Get promotion counts per game for recurring detection
    promo_counts = {}
    with db.get_connection() as conn:
        for row in conn.execute("SELECT game_id, COUNT(*) as cnt FROM promotions GROUP BY game_id"):
            promo_counts[row['game_id']] = row['cnt']

    # Format games for JSON export
    def format_game(game):
        original_price = None
        currency = None
        if game.get('original_price_cents') is not None and game.get('original_price_cents') > 0:
            original_price = game['original_price_cents'] / 100.0
            currency = game.get('currency_code', 'USD')

        # Compute free duration in hours
        duration_hours = None
        if game.get('start_date') and game.get('end_date'):
            try:
                from datetime import datetime as dt
                s = dt.fromisoformat(str(game['start_date']).replace('Z', '+00:00'))
                e = dt.fromisoformat(str(game['end_date']).replace('Z', '+00:00'))
                duration_hours = round((e - s).total_seconds() / 3600, 1)
            except (ValueError, TypeError):
                pass

        free_count = promo_counts.get(game['id'], 1)

        return {
            'id': game['id'],
            'epicId': game['epic_id'],
            'name': game['name'],
            'link': game['link'],
            'platform': game['platform'],
            'rating': game['epic_rating'],
            'image': f"images/{game['image_filename']}" if game['image_filename'] else None,
            'originalPrice': original_price,
            'currency': currency,
            'description': game.get('description'),
            'sellerName': game.get('seller_name'),
            'offerType': game.get('offer_type'),
            'effectiveDate': game.get('effective_date'),
            'viewableDate': game.get('viewable_date'),
            'expiryDate': game.get('expiry_date'),
            'tagIds': game.get('tag_ids'),
            'tagNames': resolve_tag_names(game.get('tag_ids')),
            'firstFreeDate': game.get('first_free_date'),
            'lastFreeDate': game.get('last_free_date'),
            'startDate': game.get('start_date'),
            'endDate': game.get('end_date'),
            'freeDurationHours': duration_hours,
            'freeCount': free_count,
            'status': game.get('all_statuses', '').split(',')[0] if game.get('all_statuses') else None,
        }

    # Format price statistics
    total_value = stats.get('total_value_cents')
    avg_price = stats.get('avg_price_cents')
    current_year_value = stats.get('current_year_value_cents')
    
    # Convert cents to currency units for display
    # Check what currency most games use (default to GBP for UK)
    total_value_display = total_value / 100.0 if total_value else None
    avg_price_display = avg_price / 100.0 if avg_price else None
    current_year_value_display = current_year_value / 100.0 if current_year_value else None
    
    # Determine currency from current games data
    currency_code = 'GBP'
    for g in current_games_pc:
        gc = g.get('currency_code')
        if gc:
            currency_code = gc
            break

    # Get seller stats
    seller_stats = []
    try:
        raw_sellers = db.get_seller_stats(20)
        for s in raw_sellers:
            if s.get('seller_name'):
                seller_stats.append({
                    'name': s['seller_name'],
                    'gameCount': s['game_count'],
                    'totalValue': (s.get('total_value_cents') or 0) / 100.0,
                })
    except Exception:
        pass

    # Create main data export with all platforms
    data_export = {
        'lastUpdated': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'sellerStats': seller_stats,
        'statistics': {
            'totalGames': platform_counts.get('PC', 0),
            'totalGamesIOS': platform_counts.get('iOS', 0),
            'totalGamesAndroid': platform_counts.get('Android', 0),
            'totalPromotions': stats.get('total_promotions', 0),
            'firstGameDate': stats.get('first_game_date'),
            'avgGamesPerWeek': stats.get('avg_games_per_week', 0),
            'gamesByYear': games_by_year,
            'totalValue': total_value_display,
            'avgPrice': avg_price_display,
            'currentYearValue': current_year_value_display,
            'currency': currency_code,
        },
        'currentGames': [format_game(g) for g in current_games_pc],
        'upcomingGames': [format_game(g) for g in upcoming_games_pc],
        'allGames': [format_game(g) for g in all_games_pc],
        'allGamesIOS': [format_game(g) for g in all_games_ios],
        'allGamesAndroid': [format_game(g) for g in all_games_android],
        'gamesByPlatform': {
            'PC': [format_game(g) for g in all_games_pc],
            'iOS': [format_game(g) for g in all_games_ios],
            'Android': [format_game(g) for g in all_games_android],
        },
    }

    # Save main data file (atomic write: temp file then rename)
    data_file = 'website/data/games.json'
    ensure_directory('website/data')
    tmp = data_file + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data_export, f, indent=2, ensure_ascii=False)
        os.replace(tmp, data_file)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise

    print(f"Exported {len(all_games_pc)} PC, {len(all_games_ios)} iOS, {len(all_games_android)} Android games to {data_file}")
    return data_export

def format_price(amount, currency='GBP'):
    """Format price amount with currency symbol"""
    if amount is None or amount == 0:
        return '£0'
    
    # Format with currency symbol
    if currency == 'GBP':
        return f'£{amount:,.0f}'
    elif currency == 'USD':
        return f'${amount:,.0f}'
    else:
        return f'{amount:,.0f} {currency}'

def generate_html(data):
    """Generate index.html from template"""
    print("Generating HTML...")

    current_games = data['currentGames']
    stats = data['statistics']
    currency = stats.get('currency', 'GBP')
    current_year_value = stats.get('currentYearValue', 0)

    # Build conditional current year value stat card
    current_year = datetime.now(timezone.utc).strftime('%Y')
    current_year_stat = ''
    if current_year_value:
        current_year_stat = f'''<div class="stat-card">
                    <div class="stat-number">{format_price(current_year_value, currency)}</div>
                    <div class="stat-label">{current_year} Value</div>
                </div>'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Epic Games Free Games History - Tracking {stats['totalGames']}+ Free Games Since 2018</title>
    <meta name="description" content="Complete history of free PC, iOS, and Android games given away by Epic Games Store. Track {stats['totalGames']}+ free games given away since 2018.">
    <meta property="og:title" content="Epic Games Free Games History">
    <meta property="og:description" content="Complete archive of {stats['totalGames']}+ free games from Epic Games Store since 2018. Browse the full history of every free game.">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://evenwebb.github.io/epic-free-games-scraper/">
    <meta property="og:site_name" content="Epic Games Free Games Tracker">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Epic Games Free Games History">
    <meta name="twitter:description" content="Complete archive of {stats['totalGames']}+ free games from Epic Games Store.">
    <link rel="manifest" href="/epic-free-games-scraper/manifest.json">
    <link rel="alternate" type="application/rss+xml" title="Epic Games Free Games RSS" href="/epic-free-games-scraper/feed.xml">
    <link rel="alternate" type="application/atom+xml" title="Epic Games Free Games Atom" href="/epic-free-games-scraper/feed.xml">
    <link rel="stylesheet" href="css/styles.css">
    <link rel="stylesheet" href="css/timeline.css">
</head>
<body>
    <!-- GitHub Corner Badge -->
    <a href="https://github.com/evenwebb/epic-free-games-scraper" class="github-corner" aria-label="View source on GitHub" target="_blank" rel="noopener">
        <svg width="80" height="80" viewBox="0 0 250 250" style="fill:#0078f2; color:#fff; position: fixed; top: 0; border: 0; right: 0; z-index: 1000;" aria-hidden="true">
            <path d="M0,0 L115,115 L130,115 L142,142 L250,250 L250,0 Z"></path>
            <path d="M128.3,109.0 C113.8,99.7 119.0,89.6 119.0,89.6 C122.0,82.7 120.5,78.6 120.5,78.6 C119.2,72.0 123.4,76.3 123.4,76.3 C127.3,80.9 125.5,87.3 125.5,87.3 C122.9,97.6 130.6,101.9 134.4,103.2" fill="currentColor" style="transform-origin: 130px 106px;" class="octo-arm"></path>
            <path d="M115.0,115.0 C114.9,115.1 118.7,116.5 119.8,115.4 L133.7,101.6 C136.9,99.2 139.9,98.4 142.2,98.6 C133.8,88.0 127.5,74.4 143.8,58.0 C148.5,53.4 154.0,51.2 159.7,51.0 C160.3,49.4 163.2,43.6 171.4,40.1 C171.4,40.1 176.1,42.5 178.8,56.2 C183.1,58.6 187.2,61.8 190.9,65.4 C194.5,69.0 197.7,73.2 200.1,77.6 C213.8,80.2 216.3,84.9 216.3,84.9 C212.7,93.1 206.9,96.0 205.4,96.6 C205.1,102.4 203.0,107.8 198.3,112.5 C181.9,128.9 168.3,122.5 157.7,114.1 C157.9,116.9 156.7,120.9 152.7,124.9 L141.0,136.5 C139.8,137.7 141.6,141.9 141.8,141.8 Z" fill="currentColor" class="octo-body"></path>
        </svg>
    </a>
    <style>.github-corner:hover .octo-arm{{animation:octocat-wave 560ms ease-in-out}}@keyframes octocat-wave{{0%,100%{{transform:rotate(0)}}20%,60%{{transform:rotate(-25deg)}}40%,80%{{transform:rotate(10deg)}}}}@media (max-width:500px){{.github-corner:hover .octo-arm{{animation:none}}.github-corner .octo-arm{{animation:octocat-wave 560ms ease-in-out}}}}</style>

    <header class="site-header">
        <div class="container">
            <h1>Epic Games Free Games History</h1>
            <p class="subtitle">Complete archive of free PC games since 2018</p>
            <p class="last-updated">Last updated: {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}</p>
            <button id="themeToggle" class="theme-toggle" aria-label="Toggle dark/light mode" title="Toggle theme">&#9788;</button>
        </div>
    </header>

    <!-- Current Free Games Hero Section -->
    <section class="hero-section" id="current-games">
        <div class="container">
            <h2>Free Right Now! 🎮</h2>
            <div class="current-games-grid">
                {generate_current_games_html(current_games)}
            </div>
        </div>
    </section>

    <!-- Statistics Dashboard -->
    <section class="stats-section" id="statistics">
        <div class="container">
            <h2>Statistics</h2>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number">{stats['totalGames']}</div>
                    <div class="stat-label">Total Games</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{len(data['currentGames'])}</div>
                    <div class="stat-label">Free Now</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{stats['totalPromotions']}</div>
                    <div class="stat-label">Total Promotions</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{stats['avgGamesPerWeek']:.1f}</div>
                    <div class="stat-label">Games/Week</div>
                </div>
                {current_year_stat}
            </div>
            <div class="chart-container">
                <canvas id="gamesChart"></canvas>
            </div>
        </div>
    </section>

    <!-- Search and Filter Controls -->
    <section class="search-section" id="search">
        <div class="container">
            <div class="search-controls">
                <input type="search" id="gameSearch" placeholder="Search games..." class="search-input">
                <select id="platformFilter" class="filter-select">
                    <option value="all">All Platforms</option>
                    <option value="PC">PC</option>
                    <option value="iOS">iOS</option>
                    <option value="Android">Android</option>
                </select>
                <select id="offerTypeFilter" class="filter-select">
                    <option value="all">All Types</option>
                    <option value="BASE_GAME">Full Games</option>
                    <option value="ADD_ON">Add-ons</option>
                    <option value="DLC">DLC</option>
                    <option value="EDITION">Editions</option>
                    <option value="BUNDLE">Bundles</option>
                </select>
                <select id="yearFilter" class="filter-select">
                    <option value="all">All Years</option>
                    {generate_year_options(stats['gamesByYear'])}
                </select>
                <select id="sortOrder" class="filter-select">
                    <option value="newest">Newest First</option>
                    <option value="oldest">Oldest First</option>
                    <option value="alpha">A-Z</option>
                    <option value="rating">Highest Rated</option>
                </select>
            </div>
        </div>
    </section>

    <!-- Upcoming Free Games -->
    <section class="upcoming-section" id="upcoming-games">
        <div class="container">
            <h2>Coming Soon - Next Free Games</h2>
            <div id="upcomingGamesGrid" class="upcoming-games-grid">
                <!-- Upcoming games will be populated by JavaScript -->
            </div>
        </div>
    </section>

    <!-- Timeline View -->
    <section class="timeline-section" id="timeline">
        <div class="container">
            <h2>Complete History</h2>
            <div id="gameTimeline" class="timeline">
                <!-- Timeline will be populated by JavaScript -->
            </div>
            <div id="loadingMessage" class="loading">Loading games...</div>
            <div id="noResults" class="no-results" style="display: none;">No games found matching your filters.</div>
        </div>
    </section>

    <footer class="site-footer">
        <div class="container">
            <div class="footer-content">
                <div class="footer-section">
                    <h3>About</h3>
                    <p>Data sourced from Epic Games Store API. Not affiliated with Epic Games.</p>
                    <p>This is a fan-made archive to track the history of free games.</p>
                </div>
                <div class="footer-section">
                    <h3>Open Source</h3>
                    <p>
                        <a href="https://github.com/evenwebb/epic-free-games-scraper" target="_blank" rel="noopener">
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" style="vertical-align: middle; margin-right: 4px;">
                                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
                            </svg>
                            View on GitHub
                        </a>
                    </p>
                    <p>
                        <a href="https://github.com/evenwebb" target="_blank" rel="noopener">
                            Created by evenwebb
                        </a>
                    </p>
                </div>
                <div class="footer-section">
                    <h3>Stats</h3>
                    <p>{stats['totalGames']} games tracked</p>
                    <p>Since {stats.get('firstGameDate', '2018')[:4]}</p>
                    <p>Updated daily at 4pm UK time</p>
                </div>
            </div>
            <div class="footer-bottom">
                <p>&copy; {datetime.now(timezone.utc).strftime('%Y')} Epic Free Games Tracker. GPL-3.0 License.</p>
            </div>
        </div>
    </footer>

    <!-- Back to Top Button -->
    <button id="backToTop" class="back-to-top" aria-label="Back to top">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="18 15 12 9 6 15"></polyline>
        </svg>
    </button>

    <!-- Load Chart.js for statistics visualization -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>

    <!-- Load our JavaScript -->
    <script src="js/app.js"></script>
    <script src="js/upcoming.js"></script>
    <script src="js/timeline.js"></script>
    <script src="js/stats.js"></script>
    <script src="js/search.js"></script>

    <!-- Theme toggle, PWA, countdown init -->
    <script>
        // Dark/light mode toggle
        (function() {{
            const saved = localStorage.getItem('theme');
            if (saved === 'light') document.body.classList.add('light-mode');
            else if (saved === 'dark') document.body.classList.add('dark-mode');
            const btn = document.getElementById('themeToggle');
            if (btn) {{
                btn.addEventListener('click', () => {{
                    const isLight = document.body.classList.toggle('light-mode');
                    document.body.classList.remove('dark-mode');
                    localStorage.setItem('theme', isLight ? 'light' : 'dark');
                    btn.innerHTML = isLight ? '&#9790;' : '&#9788;';
                }});
            }}
        }})();

        // PWA service worker
        if ('serviceWorker' in navigator) {{
            navigator.serviceWorker.register('/epic-free-games-scraper/sw.js');
        }}

        // Back to Top
        const backToTopButton = document.getElementById('backToTop');
        window.addEventListener('scroll', () => {{
            if (window.pageYOffset > 300) {{
                backToTopButton.classList.add('visible');
            }} else {{
                backToTopButton.classList.remove('visible');
            }}
        }});
        backToTopButton.addEventListener('click', () => {{
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }});
    </script>
</body>
</html>
'''

    # Write HTML file (atomic write)
    html_path = 'website/index.html'
    tmp = html_path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(html)
        os.replace(tmp, html_path)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise

    print("Generated index.html")

def escape(s):
    """Escape HTML to prevent XSS."""
    return html.escape(str(s)) if s is not None else ''

def generate_current_games_html(games):
    """Generate HTML for current free games cards"""
    if not games:
        return '<p class="no-games">No free games available right now.</p>'

    html_parts = []
    for game in games:
        name = escape(game["name"])
        img_src = escape(game["image"]) if game.get('image') else ''
        image_html = f'<img src="{img_src}" alt="{name}" loading="lazy">' if game.get('image') else '<div class="no-image">No Image</div>'

        price_html = ''
        if game.get('originalPrice') and game.get('originalPrice') > 0:
            currency = game.get('currency', 'GBP')
            price_html = f'<div class="game-price">Value: {format_price(game["originalPrice"], currency)}</div>'

        start_date_html = ''
        if game.get('startDate'):
            try:
                start_date = datetime.fromisoformat(game['startDate'].replace('Z', '+00:00'))
                start_date_html = f'<div class="game-start-date">Available since: {start_date.strftime("%B %d, %Y")}</div>'
            except (ValueError, TypeError, OSError):
                pass

        seller_html = ''
        seller = game.get('sellerName')
        if seller:
            seller_html = f'<div class="game-seller">{escape(seller)}</div>'

        duration_badge = ''
        dur = game.get('freeDurationHours')
        if dur:
            days = int(dur / 24)
            label = f'{days} days' if days >= 1 else f'{int(dur)} hours'
            duration_badge = f'<span class="badge badge-duration">Free for {label}</span>'

        recurring_badge = ''
        fc = game.get('freeCount', 1)
        if fc > 1:
            recurring_badge = f'<span class="badge badge-recurring">Previously free {fc - 1}x</span>'

        desc = game.get('description')
        desc_html = f'<p class="game-desc">{escape(desc)}</p>' if desc else ''

        html_parts.append(f'''
            <div class="hero-card">
                <div class="hero-card-image">
                    {image_html}
                </div>
                <div class="hero-card-content">
                    <h3>{name}</h3>
                    {seller_html}
                    {start_date_html}
                    {price_html}
                    {duration_badge} {recurring_badge}
                    {desc_html}
                    <div class="countdown" data-end="{game.get("endDate", "")}">Time remaining...</div>
                    <a href="{escape(game["link"])}" target="_blank" rel="noopener" class="cta-button">Get It Free</a>
                </div>
            </div>
        ''')

    return '\n'.join(html_parts)

def generate_year_options(games_by_year):
    """Generate year filter options"""
    years = sorted(games_by_year.keys(), reverse=True)
    return '\n'.join([f'<option value="{year}">{year}</option>' for year in years])

def generate_manifest():
    """Generate PWA manifest.json."""
    manifest = {
        'name': 'Epic Games Free Games Tracker',
        'short_name': 'Epic Free Games',
        'description': 'Complete history of free games from Epic Games Store',
        'start_url': '/epic-free-games-scraper/',
        'display': 'standalone',
        'background_color': '#0a0a0a',
        'theme_color': '#0078f2',
        'icons': [{'src': 'images/favicon.svg', 'sizes': 'any', 'type': 'image/svg+xml'}],
    }
    path = 'website/manifest.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    print(f"Generated {path}")


def generate_sw():
    """Generate minimal service worker for offline caching."""
    sw = """const CACHE = 'epic-free-games-v1';
const URLS = ['/epic-free-games-scraper/', '/epic-free-games-scraper/css/styles.css',
    '/epic-free-games-scraper/css/timeline.css', '/epic-free-games-scraper/js/app.js',
    '/epic-free-games-scraper/js/search.js', '/epic-free-games-scraper/js/timeline.js',
    '/epic-free-games-scraper/data/games.json'];
self.addEventListener('install', e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(URLS))));
self.addEventListener('fetch', e => e.respondWith(caches.match(e.request).then(r => r || fetch(e.request))));
"""
    with open('website/sw.js', 'w', encoding='utf-8') as f:
        f.write(sw)
    print("Generated website/sw.js")


def generate_rss(data):
    """Generate RSS/Atom feed for new free games."""
    stats = data['statistics']
    games = data['allGames'][:50]
    now_iso = datetime.now(timezone.utc).isoformat()
    items = []
    for g in games:
        title = html.escape(g['name'])
        link = html.escape(g['link'])
        desc = html.escape(g.get('description') or g['name'])
        date = g.get('firstFreeDate') or now_iso
        items.append(f"""    <item>
      <title>{title}</title>
      <link>{link}</link>
      <description>{desc}</description>
      <pubDate>{date}</pubDate>
      <guid isPermaLink="false">{g['epicId']}-{date}</guid>
    </item>""")
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Epic Games Free Games</title>
    <link>https://evenwebb.github.io/epic-free-games-scraper/</link>
    <description>Complete history of {stats['totalGames']}+ free games from Epic Games Store</description>
    <atom:link href="https://evenwebb.github.io/epic-free-games-scraper/feed.xml" rel="self" type="application/rss+xml"/>
    <lastBuildDate>{now_iso}</lastBuildDate>
{chr(10).join(items)}
  </channel>
</rss>"""
    with open('website/feed.xml', 'w', encoding='utf-8') as f:
        f.write(feed)
    print("Generated website/feed.xml")


def generate_ics(data):
    """Generate iCalendar file for upcoming free games."""
    upcoming = data.get('upcomingGames', [])
    now_utc = datetime.now(timezone.utc)
    events = []
    for g in upcoming:
        try:
            start = datetime.fromisoformat(g['startDate'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(g['endDate'].replace('Z', '+00:00'))
        except (ValueError, TypeError, KeyError):
            continue
        uid = f"{g['epicId']}-{start.strftime('%Y%m%d')}@epic-free-games"
        events.append(f"""BEGIN:VEVENT
UID:{uid}
DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:{g['name']} - FREE on Epic Games
DESCRIPTION:Claim free at {g['link']}
CATEGORIES:Games
END:VEVENT""")
    ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Epic Free Games Tracker//EN
X-WR-CALNAME:Epic Games Free Games
X-PUBLISHED-TTL:PT12H
REFRESH-INTERVAL;VALUE=DURATION:PT12H
METHOD:PUBLISH
{chr(10).join(events) if events else ''}
END:VCALENDAR
"""
    with open('website/calendar.ics', 'w', encoding='utf-8') as f:
        f.write(ics)
    print(f"Generated website/calendar.ics ({len(upcoming)} upcoming games)")


def generate_api_latest(data):
    """Generate minimal /api/latest.json endpoint for bots/scripts."""
    current = data.get('currentGames', [])
    latest = {
        'updated': data['lastUpdated'],
        'freeNow': [{'name': g['name'], 'link': g['link'],
                      'endDate': g.get('endDate'), 'seller': g.get('sellerName'),
                      'originalPrice': g.get('originalPrice'), 'currency': g.get('currency')}
                     for g in current],
        'upcoming': [{'name': g['name'], 'link': g['link'],
                       'startDate': g.get('startDate'), 'endDate': g.get('endDate'),
                       'seller': g.get('sellerName')}
                      for g in data.get('upcomingGames', [])[:5]],
    }
    ensure_directory('website/api')
    with open('website/api/latest.json', 'w', encoding='utf-8') as f:
        json.dump(latest, f, indent=2, ensure_ascii=False)
    print(f"Generated website/api/latest.json ({len(current)} current, {len(data.get('upcomingGames', []))} upcoming)")


def generate_game_pages(data):
    """Generate individual game detail pages."""
    all_games = data['allGames']
    ensure_directory('website/game')
    count = 0
    for g in all_games:
        slug = g['epicId']
        name = html.escape(g['name'])
        seller = html.escape(g.get('sellerName') or 'Unknown')
        desc = html.escape(g.get('description') or '')
        link = html.escape(g['link'])
        img = html.escape(g.get('image') or '')
        price = g.get('originalPrice')
        currency = g.get('currency', 'GBP')
        price_str = format_price(price, currency) if price else 'Unknown'
        dur = g.get('freeDurationHours')
        dur_str = f"{int(dur/24)} days" if dur and dur >= 24 else (f"{int(dur)} hours" if dur else 'Unknown')
        fc = g.get('freeCount', 1)
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name} - Epic Games Free Games History</title>
    <meta name="description" content="{desc[:160]}">
    <link rel="stylesheet" href="../css/styles.css">
</head>
<body>
    <header class="site-header">
        <div class="container">
            <a href="../">&larr; Back to all games</a>
            <h1>{name}</h1>
        </div>
    </header>
    <main class="container game-detail">
        <div class="game-detail-layout">
            {f'<img src="../{img}" alt="{name}" class="game-detail-image">' if img else ''}
            <div class="game-detail-info">
                <p><strong>Seller:</strong> {seller}</p>
                <p><strong>Normal price:</strong> {price_str}</p>
                <p><strong>Free duration:</strong> {dur_str}</p>
                {f'<p><strong>Previously free:</strong> {fc - 1} times</p>' if fc > 1 else ''}
                {f'<p class="game-detail-desc">{desc}</p>' if desc else ''}
                <a href="{link}" target="_blank" rel="noopener" class="cta-button">View on Epic Games Store</a>
            </div>
        </div>
    </main>
</body>
</html>"""
        with open(f'website/game/{slug}.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        count += 1
    print(f"Generated {count} game detail pages in website/game/")


def generate_website():
    """Main function to generate complete website"""
    print("=" * 60)
    print("Epic Games Free Games Website Generator")
    print("=" * 60)

    # Initialize database
    db = DatabaseManager()

    # Create website directory structure
    print("\nCreating directory structure...")
    directories = [
        'website',
        'website/css',
        'website/js',
        'website/data',
        'website/images',
        'website/api',
        'website/game',
    ]
    for directory in directories:
        ensure_directory(directory)

    # Export data
    data = export_data_json(db)

    # Generate all files
    generate_html(data)
    generate_manifest()
    generate_sw()
    generate_rss(data)
    generate_ics(data)
    generate_api_latest(data)
    generate_game_pages(data)

    # Copy images
    copy_images(db)

    print("\n" + "=" * 60)
    print("Website generation complete!")
    print(f"Website location: {os.path.abspath('website/')}")
    print(f"Open website/index.html in your browser to view")
    print("=" * 60)

if __name__ == '__main__':
    generate_website()
