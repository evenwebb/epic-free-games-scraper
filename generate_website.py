#!/usr/bin/env python3
"""
Generate static website from the Epic Games free games database.
Creates a complete static site with HTML, CSS, JS, and data files.
"""

import json
import os
import shutil
from datetime import datetime, timezone
from db_manager import DatabaseManager

def ensure_directory(path):
    """Create directory if it doesn't exist"""
    os.makedirs(path, exist_ok=True)

def copy_images():
    """
    Incrementally sync game images to website directory.

    Performance: Only copies new/changed files instead of all images.
    """
    source = 'output/images'
    dest = 'website/images'

    if not os.path.exists(source):
        print("Warning: No images directory found")
        ensure_directory(dest)
        return

    ensure_directory(dest)

    # Get list of source and destination files
    source_files = set(os.listdir(source)) if os.path.exists(source) else set()
    dest_files = set(os.listdir(dest)) if os.path.exists(dest) else set()

    copied = 0
    skipped = 0
    removed = 0

    # Copy new or modified images
    for filename in source_files:
        if filename.endswith(('.jpg', '.png', '.jpeg')):
            source_path = os.path.join(source, filename)
            dest_path = os.path.join(dest, filename)

            # Check if file needs copying (new or modified)
            needs_copy = True
            if os.path.exists(dest_path):
                # Compare modification times
                source_mtime = os.path.getmtime(source_path)
                dest_mtime = os.path.getmtime(dest_path)
                source_size = os.path.getsize(source_path)
                dest_size = os.path.getsize(dest_path)

                # Skip if same size and destination is newer or same age
                if source_size == dest_size and dest_mtime >= source_mtime:
                    needs_copy = False
                    skipped += 1

            if needs_copy:
                shutil.copy2(source_path, dest_path)  # copy2 preserves metadata
                copied += 1

    # Remove images that no longer exist in source
    for filename in dest_files:
        if filename.endswith(('.jpg', '.png', '.jpeg')) and filename not in source_files:
            dest_path = os.path.join(dest, filename)
            os.remove(dest_path)
            removed += 1

    total_images = len([f for f in dest_files.union(source_files) if f.endswith(('.jpg', '.png', '.jpeg'))])
    print(f"Images sync: {copied} copied, {skipped} skipped, {removed} removed ({total_images} total)")

def export_data_json(db):
    """Export database data to JSON for website consumption"""
    print("Exporting data from database...")

    # Get statistics
    stats = db.get_statistics()
    platform_counts = db.get_platform_counts()
    games_by_year = db.get_games_by_year()

    # Get current, upcoming, and all games (PC only)
    current_games = db.get_current_games(platform='PC')
    upcoming_games = db.get_upcoming_games(platform='PC')
    all_games = db.get_all_games_chronological(platform='PC')

    # Format games for JSON export
    def format_game(game):
        # Format price if available
        original_price = None
        currency = None
        if game.get('original_price_cents') is not None and game.get('original_price_cents') > 0:
            original_price = game['original_price_cents'] / 100.0  # Convert cents to dollars
            currency = game.get('currency_code', 'USD')
        
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
            'firstFreeDate': game.get('first_free_date'),
            'lastFreeDate': game.get('last_free_date'),
            'startDate': game.get('start_date'),
            'endDate': game.get('end_date'),
            'status': game.get('all_statuses', '').split(',')[0] if game.get('all_statuses') else None
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
    
    # Determine currency from stats (most common currency in database)
    # For now default to GBP since we're using UK region
    currency_code = 'GBP'

    # Create main data export (PC only)
    data_export = {
        'lastUpdated': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'statistics': {
            'totalGames': platform_counts.get('PC', 0),
            'totalPromotions': stats.get('total_promotions', 0),
            'firstGameDate': stats.get('first_game_date'),
            'avgGamesPerWeek': stats.get('avg_games_per_week', 0),
            'gamesByYear': games_by_year,
            'totalValue': total_value_display,
            'avgPrice': avg_price_display,
            'currentYearValue': current_year_value_display,
            'currency': currency_code
        },
        'currentGames': [format_game(g) for g in current_games],
        'upcomingGames': [format_game(g) for g in upcoming_games],
        'allGames': [format_game(g) for g in all_games]
    }

    # Save main data file
    data_file = 'website/data/games.json'
    ensure_directory('website/data')
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data_export, f, indent=2, ensure_ascii=False)

    print(f"Exported {len(all_games)} games to {data_file}")
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

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Epic Games Free Games History - Tracking {stats['totalGames']}+ Free Games Since 2018</title>
    <meta name="description" content="Complete history of free PC games given away by Epic Games Store since 2018. Track {stats['totalGames']}+ games.">
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
                {f'''<div class="stat-card">
                    <div class="stat-number">{format_price(current_year_value, currency)}</div>
                    <div class="stat-label">2026 Value</div>
                </div>''' if current_year_value else ''}
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
                    <p>Updated every 6 hours</p>
                </div>
            </div>
            <div class="footer-bottom">
                <p>&copy; 2024 Epic Free Games Tracker. MIT License.</p>
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

    <!-- Back to Top functionality -->
    <script>
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

    # Write HTML file
    with open('website/index.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print("Generated index.html")

def generate_current_games_html(games):
    """Generate HTML for current free games cards"""
    if not games:
        return '<p class="no-games">No free games available right now.</p>'

    html_parts = []
    for game in games:
        # Add lazy loading to images
        image_html = f'<img src="{game["image"]}" alt="{game["name"]}" loading="lazy">' if game.get('image') else '<div class="no-image">No Image</div>'

        html_parts.append(f'''
            <div class="hero-card">
                <div class="hero-card-image">
                    {image_html}
                </div>
                <div class="hero-card-content">
                    <h3>{game["name"]}</h3>
                    <div class="countdown" data-end="{game.get("endDate", "")}">Time remaining...</div>
                    <a href="{game["link"]}" target="_blank" rel="noopener" class="cta-button">Get It Free</a>
                </div>
            </div>
        ''')

    return '\n'.join(html_parts)

def generate_year_options(games_by_year):
    """Generate year filter options"""
    years = sorted(games_by_year.keys(), reverse=True)
    return '\n'.join([f'<option value="{year}">{year}</option>' for year in years])

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
        'website/images'
    ]
    for directory in directories:
        ensure_directory(directory)

    # Export data
    data = export_data_json(db)

    # Generate HTML
    generate_html(data)

    # Copy images
    copy_images()

    print("\n" + "=" * 60)
    print("Website generation complete!")
    print(f"Website location: {os.path.abspath('website/')}")
    print(f"Open website/index.html in your browser to view")
    print("=" * 60)

if __name__ == '__main__':
    generate_website()
