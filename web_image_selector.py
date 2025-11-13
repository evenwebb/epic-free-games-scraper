#!/usr/bin/env python3
"""
Web-based image selector for games without images.
Opens a browser interface where you can click to select the correct image.
"""

from flask import Flask, render_template_string, request, redirect, url_for
import requests
import os
import re
import random
from urllib.parse import quote_plus
from db_manager import DatabaseManager
from PIL import Image
from io import BytesIO

app = Flask(__name__)

# User agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
]

def get_games_without_images():
    """Get all games that don't have images"""
    db = DatabaseManager()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, epic_id, name, link, platform
            FROM games
            WHERE image_filename IS NULL OR image_filename = ''
            ORDER BY created_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

def search_google_images(game_name, max_results=15, restrict_site=True):
    """
    Search Google Images for a game and return landscape images only.

    Args:
        game_name: Name of the game
        max_results: Maximum number of results to fetch
        restrict_site: If True, restrict to epicgames.com. If False, search all sites.

    Returns:
        List of dicts with 'url', 'width', 'height', 'is_landscape'
    """
    # Search query: optionally restrict to site:epicgames.com
    if restrict_site:
        query = f"site:epicgames.com {game_name}"
    else:
        query = game_name
    search_url = f"https://www.google.com/search?q={quote_plus(query)}&tbm=isch"

    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.google.com/',
    }

    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()

        # Extract image URLs from the HTML
        # Google Images embeds JSON data in the HTML
        pattern = r'\["(https://[^"]+\.(jpg|jpeg|png|webp))",(\d+),(\d+)\]'
        matches = re.findall(pattern, response.text, re.IGNORECASE)

        results = []
        seen_urls = set()

        for match in matches[:max_results]:
            url = match[0]
            # Note: Google's JSON has height first, then width
            height = int(match[2])
            width = int(match[3])

            # Skip duplicates
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Calculate aspect ratio
            if height > 0:
                aspect_ratio = width / height
            else:
                aspect_ratio = 0

            # Check if landscape (aspect ratio between 1.5 and 2.5)
            is_landscape = 1.5 <= aspect_ratio <= 2.5

            # Only add landscape images
            if is_landscape:
                results.append({
                    'url': url,
                    'width': width,
                    'height': height,
                    'aspect_ratio': aspect_ratio,
                    'is_landscape': True
                })

        return results

    except Exception as e:
        print(f"Error searching Google Images: {e}")
        return []

def download_and_save_image(image_url, epic_id):
    """
    Download an image and save it as JPG.

    Args:
        image_url: URL of the image
        epic_id: Epic ID for the filename

    Returns:
        filename if successful, None otherwise
    """
    try:
        # Download image
        response = requests.get(image_url, timeout=10, stream=True)
        response.raise_for_status()

        # Open and convert to RGB
        img = Image.open(BytesIO(response.content))

        # Convert to RGB if needed
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode == 'RGBA':
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Save as JPEG
        filename = f"{epic_id}.jpg"
        output_path = os.path.join('output/images', filename)
        img.save(output_path, 'JPEG', quality=85, optimize=True)

        return filename

    except Exception as e:
        print(f"Error downloading image: {e}")
        return None

# HTML template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Select Game Image - {{ current_game['name'] }}</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .header {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            margin: 0 0 10px 0;
            color: #333;
        }
        .progress {
            color: #666;
            font-size: 14px;
        }
        .game-info {
            background: #e3f2fd;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .game-info a {
            color: #1976d2;
            text-decoration: none;
        }
        .game-info a:hover {
            text-decoration: underline;
        }
        .custom-search-box {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .images-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .image-option {
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
            cursor: pointer;
        }
        .image-option:hover {
            transform: translateY(-4px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }
        .image-option img {
            width: 100%;
            height: 200px;
            object-fit: cover;
            display: block;
        }
        .image-info {
            padding: 12px;
            font-size: 12px;
            color: #666;
            border-top: 1px solid #eee;
        }
        .no-images {
            background: #fff3e0;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            color: #e65100;
        }
        .actions {
            background: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .btn {
            display: inline-block;
            padding: 12px 24px;
            background: #1976d2;
            color: white;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 500;
            transition: background 0.2s;
        }
        .btn:hover {
            background: #1565c0;
        }
        .btn-skip {
            background: #757575;
            margin-left: 10px;
        }
        .btn-skip:hover {
            background: #616161;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Select Image for: {{ current_game['name'] }}</h1>
        <div class="progress">
            Game {{ current_index + 1 }} of {{ total_games }}
            ({{ completed }} completed, {{ remaining }} remaining)
        </div>
    </div>

    <div class="game-info">
        <strong>Epic Link:</strong> <a href="{{ current_game['link'] }}" target="_blank">{{ current_game['link'] }}</a><br>
        <strong>Platform:</strong> {{ current_game['platform'] }}<br>
        <strong>Epic ID:</strong> {{ current_game['epic_id'] }}
    </div>

    <div class="custom-search-box">
        <form method="GET" action="{{ url_for('custom_search', game_index=current_index) }}" style="display: flex; gap: 10px; align-items: center;">
            <input type="text" name="query" value="{{ custom_query or current_game['name'] }}"
                   placeholder="Enter custom search query..."
                   style="flex: 1; padding: 10px; border: 2px solid #ddd; border-radius: 6px; font-size: 14px;">
            <button type="submit" class="btn" style="margin: 0;">Custom Search</button>
        </form>
        {% if is_custom_search %}
            <p style="margin-top: 10px; color: #1976d2;">
                ⚠️ Showing results for custom search: "{{ custom_query }}" (all websites)
                <a href="{{ url_for('index', start=current_index) }}" style="color: #d32f2f; margin-left: 10px;">← Back to Epic-only results</a>
            </p>
        {% else %}
            <p style="margin-top: 10px; color: #666; font-size: 13px;">
                💡 Not finding the right image? Try a custom search above (searches all websites, not just Epic)
            </p>
        {% endif %}
    </div>

    {% if results %}
        <h2>Click an image to select ({{ results|length }} landscape images found)</h2>
        <div class="images-grid">
            {% for i, result in enumerate(results) %}
                <a href="{{ url_for('select_image', game_index=current_index, image_index=i, custom_query=custom_query if is_custom_search else None) }}" class="image-option">
                    <img src="{{ result['url'] }}" alt="Option {{ i + 1 }}" loading="lazy">
                    <div class="image-info">
                        {{ result['width'] }}x{{ result['height'] }}
                        ({{ "%.2f"|format(result['aspect_ratio']) }}:1 aspect ratio)
                    </div>
                </a>
            {% endfor %}
        </div>
    {% else %}
        <div class="no-images">
            <h2>⚠️ No landscape images found</h2>
            <p>No suitable landscape images (1.5:1 to 2.5:1 aspect ratio) were found for this game.</p>
            <p>This could mean:</p>
            <ul style="text-align: left; display: inline-block;">
                <li>The game doesn't have proper hero images on Epic</li>
                <li>Google hasn't indexed the images yet</li>
                <li>The game name needs manual searching</li>
            </ul>
        </div>
    {% endif %}

    <div class="actions">
        <a href="{{ url_for('skip_game', game_index=current_index) }}" class="btn btn-skip">Skip This Game</a>
        {% if current_index > 0 %}
            <a href="{{ url_for('index', start=current_index - 1) }}" class="btn btn-skip">← Previous</a>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    """Main page - show current game and image options"""
    games = get_games_without_images()

    if not games:
        return "<h1>✅ All games have images!</h1><p>No games without images found.</p>"

    # Get start index from query param
    start = request.args.get('start', 0, type=int)

    if start >= len(games):
        return "<h1>✅ Finished!</h1><p>You've reviewed all games without images.</p>"

    current_game = games[start]

    # Search for images (Epic site only by default)
    results = search_google_images(current_game['name'], restrict_site=True)

    return render_template_string(
        HTML_TEMPLATE,
        current_game=current_game,
        results=results,
        current_index=start,
        total_games=len(games),
        completed=start,
        remaining=len(games) - start,
        is_custom_search=False,
        custom_query=None,
        enumerate=enumerate
    )

@app.route('/custom/<int:game_index>')
def custom_search(game_index):
    """Handle custom search with user-provided query"""
    games = get_games_without_images()

    if game_index >= len(games):
        return redirect(url_for('index'))

    current_game = games[game_index]
    custom_query = request.args.get('query', current_game['name'])

    # Search without site restriction
    results = search_google_images(custom_query, restrict_site=False)

    return render_template_string(
        HTML_TEMPLATE,
        current_game=current_game,
        results=results,
        current_index=game_index,
        total_games=len(games),
        completed=game_index,
        remaining=len(games) - game_index,
        is_custom_search=True,
        custom_query=custom_query,
        enumerate=enumerate
    )

@app.route('/select/<int:game_index>/<int:image_index>')
def select_image(game_index, image_index):
    """Handle image selection"""
    games = get_games_without_images()

    if game_index >= len(games):
        return redirect(url_for('index'))

    game = games[game_index]

    # Check if this was from a custom search
    custom_query = request.args.get('custom_query')

    # Search again to get the selected image URL
    if custom_query:
        results = search_google_images(custom_query, restrict_site=False)
    else:
        results = search_google_images(game['name'], restrict_site=True)

    if image_index >= len(results):
        return redirect(url_for('index', start=game_index))

    selected_image = results[image_index]

    # Download and save the image
    filename = download_and_save_image(selected_image['url'], game['epic_id'])

    if filename:
        # Update database
        db = DatabaseManager()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE games
                SET image_filename = ?
                WHERE id = ?
            """, (filename, game['id']))

        print(f"✅ Saved image for {game['name']}: {filename}")
    else:
        print(f"❌ Failed to save image for {game['name']}")

    # Move to next game
    return redirect(url_for('index', start=game_index + 1))

@app.route('/skip/<int:game_index>')
def skip_game(game_index):
    """Skip current game and move to next"""
    return redirect(url_for('index', start=game_index + 1))

if __name__ == '__main__':
    print("=" * 60)
    print("Web Image Selector for Epic Games")
    print("=" * 60)

    games = get_games_without_images()
    print(f"\nFound {len(games)} games without images")

    if not games:
        print("\n✅ All games already have images!")
    else:
        print("\nStarting web server...")
        print("Open your browser to: http://127.0.0.1:5000")
        print("\nPress Ctrl+C to stop the server")
        print("=" * 60)

        # Open browser automatically
        import webbrowser
        import threading

        def open_browser():
            import time
            time.sleep(1.5)  # Wait for server to start
            webbrowser.open('http://127.0.0.1:5000')

        threading.Thread(target=open_browser, daemon=True).start()

        app.run(debug=False, port=5000)
