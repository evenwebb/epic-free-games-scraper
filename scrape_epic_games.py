import json
import os
import requests
from datetime import datetime, timezone

def load_settings():
    """Load settings from the external JSON file."""
    settings_file = 'settings.json'
    if os.path.exists(settings_file):
        with open(settings_file, 'r', encoding='utf-8') as file:
            return json.load(file)
    return {}

def send_pushover_notification(user_key, app_token, title, message, image_path=None):
    """Send a Pushover notification with an optional image."""
    try:
        data = {
            "token": app_token,
            "user": user_key,
            "title": title,
            "message": message
        }
        if image_path:
            with open(image_path, "rb") as img_file:
                files = {"attachment": img_file}
                response = requests.post(
                    "https://api.pushover.net/1/messages.json", data=data, files=files
                )
        else:
            response = requests.post(
                "https://api.pushover.net/1/messages.json", data=data
            )
        if response.status_code == 200:
            print("Pushover notification sent successfully.")
        else:
            print(f"Failed to send Pushover notification: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error sending Pushover notification: {e}")

def get_game_link(game):
    """Construct the store link for a game."""
    product_slug = game.get('productSlug')
    url_slug = game.get('urlSlug')

    if product_slug:
        return f"https://store.epicgames.com/en-US/p/{product_slug}"
    elif url_slug:
        return f"https://store.epicgames.com/en-US/p/{url_slug}"
    else:
        # Fallback to catalog namespace mapping if available
        mappings = game.get('catalogNs', {}).get('mappings', [])
        if mappings:
            page_slug = mappings[0].get('pageSlug')
            if page_slug:
                return f"https://store.epicgames.com/en-US/p/{page_slug}"

    return None

def get_game_image_url(game):
    """Get the best image URL for a game."""
    key_images = game.get('keyImages', [])

    # Prefer OfferImageWide, then OfferImageTall, then Thumbnail
    for image_type in ['OfferImageWide', 'OfferImageTall', 'Thumbnail']:
        for image in key_images:
            if image.get('type') == image_type:
                return image.get('url')

    # If none of the preferred types found, return first image
    if key_images:
        return key_images[0].get('url')

    return None

def format_date(iso_date):
    """Format ISO date to human-readable format."""
    try:
        dt = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
        return dt.strftime('%b %d at %I:%M %p')
    except:
        return iso_date

def scrape_epic_free_games():
    # Load settings
    settings = load_settings()
    pushover_enabled = settings.get("pushover", {}).get("enabled", False)
    user_key = settings.get("pushover", {}).get("user_key", "")
    app_token = settings.get("pushover", {}).get("app_token", "")
    notify_always = settings.get("pushover", {}).get("notify_always", False)

    # Paths
    json_file = 'output/free_games.json'
    os.makedirs('output/images', exist_ok=True)

    # Load existing data
    existing_data = {}
    if os.path.exists(json_file):
        with open(json_file, 'r', encoding='utf-8') as file:
            existing_data = json.load(file)

    past_games = existing_data.get("Past Games", [])
    next_games = []  # Track upcoming games
    new_games = []  # Track new current games
    existing_next_game_images = []  # Track images for next games
    current_games = []  # Track current free games for notifications

    try:
        # Fetch free games from Epic Games API
        api_url = 'https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US&allowCountries=US'
        print("Fetching free games from Epic Games API...")
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()

        api_data = response.json()
        games = api_data['data']['Catalog']['searchStore']['elements']

        now = datetime.now(timezone.utc)

        # Process games
        for game in games:
            if not game.get('promotions'):
                continue

            game_title = game['title']
            game_link = get_game_link(game)

            if not game_link:
                print(f"Skipping {game_title}: no valid link found")
                continue

            # Check current promotions (free now)
            promo_offers = game['promotions'].get('promotionalOffers', [])
            if promo_offers and len(promo_offers) > 0:
                for offer_group in promo_offers:
                    for offer in offer_group.get('promotionalOffers', []):
                        start = datetime.fromisoformat(offer['startDate'].replace('Z', '+00:00'))
                        end = datetime.fromisoformat(offer['endDate'].replace('Z', '+00:00'))

                        # Only process if currently free (100% discount)
                        if start <= now <= end and offer['discountSetting']['discountPercentage'] == 0:
                            image_url = get_game_image_url(game)
                            game_id = game.get('id', game_link.split('/')[-1])
                            date_period = f"Free Now - {format_date(offer['endDate'])}"

                            # Check for duplicates
                            existing_game = next((g for g in past_games if g['Link'] == game_link), None)
                            if not existing_game:
                                new_games.append(game_title)

                                # Save image
                                if image_url:
                                    image_filename = f"{game_id}.jpg"
                                    image_path = os.path.join('output/images', image_filename)
                                    try:
                                        img_response = requests.get(image_url, timeout=10)
                                        img_response.raise_for_status()
                                        with open(image_path, 'wb') as img_file:
                                            img_file.write(img_response.content)
                                        print(f"Downloaded image for {game_title}")
                                    except Exception as e:
                                        print(f"Failed to download image for {game_title}: {e}")
                                        image_path = None
                                else:
                                    image_path = None

                                # Add to past games
                                past_games.append({
                                    'Name': game_title,
                                    'Link': game_link,
                                    'Image': image_path,
                                    'Availability': date_period
                                })
                            else:
                                image_path = existing_game.get('Image')

                            # Track current games for notifications
                            current_games.append({
                                'Name': game_title,
                                'Link': game_link,
                                'Image': image_path,
                                'Availability': date_period
                            })

            # Check upcoming promotions (free later)
            upcoming_offers = game['promotions'].get('upcomingPromotionalOffers', [])
            if upcoming_offers and len(upcoming_offers) > 0:
                for offer_group in upcoming_offers:
                    for offer in offer_group.get('promotionalOffers', []):
                        # Only process if it will be free (100% discount)
                        if offer['discountSetting']['discountPercentage'] == 0:
                            image_url = get_game_image_url(game)
                            availability = f"{format_date(offer['startDate'])} - {format_date(offer['endDate'])}"

                            # Save image with dynamic filename
                            next_game_counter = len(next_games) + 1
                            image_filename = f"next-game{next_game_counter}.jpg" if next_game_counter > 1 else "next-game.jpg"
                            image_path = os.path.join('output/images', image_filename)

                            if image_url:
                                try:
                                    img_response = requests.get(image_url, timeout=10)
                                    img_response.raise_for_status()
                                    with open(image_path, 'wb') as img_file:
                                        img_file.write(img_response.content)
                                    print(f"Downloaded image for upcoming game: {game_title}")
                                except Exception as e:
                                    print(f"Failed to download image for {game_title}: {e}")

                            existing_next_game_images.append(image_filename)

                            # Add to next games
                            next_games.append({
                                'Name': game_title,
                                'Link': game_link,
                                'Image': image_path,
                                'Availability': availability
                            })

        print(f"Found {len(current_games)} current free games")
        print(f"Found {len(next_games)} upcoming free games")

        # Cleanup old next-game images
        for filename in os.listdir('output/images'):
            if filename.startswith("next-game") and filename not in existing_next_game_images:
                os.remove(os.path.join('output/images', filename))
                print(f"Removed unused file: {filename}")

        # Notify via Pushover
        if pushover_enabled:
            if notify_always or new_games:
                if notify_always:
                    print("Pushover notifications are set to always notify.")
                    for game in current_games:  # Send notifications for all current games
                        image_path = game.get("Image")
                        if image_path and os.path.exists(image_path):
                            print(f"Image found for {game['Name']}: {image_path}")
                        else:
                            print(f"No valid image found for {game['Name']}. Image will not be attached.")
                            image_path = None  # Ensure no invalid image is passed

                        # Send the notification
                        send_pushover_notification(
                            user_key,
                            app_token,
                            title="Free Game Available!",
                            message=f"{game['Name']} is free on Epic Games Store!\nAvailability: {game['Availability']}",
                            image_path=image_path
                        )

                elif new_games:
                    print(f"New games detected: {new_games}")
                    for new_game in new_games:
                        game_data = next((game for game in past_games if game["Name"] == new_game), None)
                        if game_data:
                            image_path = game_data.get("Image")
                            if image_path and os.path.exists(image_path):
                                print(f"Image found for {new_game}: {image_path}")
                            else:
                                print(f"No valid image found for {new_game}. Image will not be attached.")
                                image_path = None

                            send_pushover_notification(
                                user_key,
                                app_token,
                                title="New Free Game Available!",
                                message=f"{new_game} is now free on Epic Games Store!\nAvailability: {game_data['Availability']}",
                                image_path=image_path
                            )

        # Save updated JSON
        updated_data = {
            "Next Games": next_games,
            "Past Games": past_games
        }
        with open(json_file, 'w', encoding='utf-8') as file:
            json.dump(updated_data, file, indent=4, ensure_ascii=False)

        print(f"Data scraped successfully. Updated data saved to {json_file}")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    scrape_epic_free_games()
