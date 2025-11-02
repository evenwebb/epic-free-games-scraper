#!/usr/bin/env python3
"""
Generate static website from the Epic Games free games database.
Creates a complete static site with HTML, CSS, JS, and data files.
"""

import json
import os
import shutil
from datetime import datetime
from db_manager import DatabaseManager

def ensure_directory(path):
    """Create directory if it doesn't exist"""
    os.makedirs(path, exist_ok=True)

def copy_images():
    """Copy game images to website directory"""
    source = 'output/images'
    dest = 'website/images'

    if os.path.exists(source):
        # Remove existing images directory
        if os.path.exists(dest):
            shutil.rmtree(dest)
        # Copy all images
        shutil.copytree(source, dest)
        image_count = len([f for f in os.listdir(dest) if f.endswith(('.jpg', '.png', '.jpeg'))])
        print(f"Copied {image_count} images to website/images/")
    else:
        print("Warning: No images directory found")
        ensure_directory(dest)

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
        return {
            'id': game['id'],
            'epicId': game['epic_id'],
            'name': game['name'],
            'link': game['link'],
            'platform': game['platform'],
            'rating': game['epic_rating'],
            'image': f"images/{game['image_filename']}" if game['image_filename'] else None,
            'firstFreeDate': game.get('first_free_date'),
            'lastFreeDate': game.get('last_free_date'),
            'startDate': game.get('start_date'),
            'endDate': game.get('end_date'),
            'status': game.get('all_statuses', '').split(',')[0] if game.get('all_statuses') else None
        }

    # Create main data export (PC only)
    data_export = {
        'lastUpdated': datetime.utcnow().isoformat() + 'Z',
        'statistics': {
            'totalGames': platform_counts.get('PC', 0),
            'totalPromotions': stats.get('total_promotions', 0),
            'firstGameDate': stats.get('first_game_date'),
            'avgGamesPerWeek': stats.get('avg_games_per_week', 0),
            'gamesByYear': games_by_year
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

def generate_html(data):
    """Generate index.html from template"""
    print("Generating HTML...")

    current_games = data['currentGames']
    stats = data['statistics']

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
    <header class="site-header">
        <div class="container">
            <h1>Epic Games Free Games History</h1>
            <p class="subtitle">Complete archive of free PC games since 2018</p>
            <p class="last-updated">Last updated: {datetime.utcnow().strftime('%B %d, %Y at %H:%M UTC')}</p>
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
            <p>Data sourced from Epic Games Store API. Not affiliated with Epic Games.</p>
            <p>This is a fan-made archive to track the history of free games.</p>
        </div>
    </footer>

    <!-- Load Chart.js for statistics visualization -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>

    <!-- Load our JavaScript -->
    <script src="js/app.js"></script>
    <script src="js/timeline.js"></script>
    <script src="js/stats.js"></script>
    <script src="js/search.js"></script>
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
        image_html = f'<img src="{game["image"]}" alt="{game["name"]}">' if game.get('image') else '<div class="no-image">No Image</div>'

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
