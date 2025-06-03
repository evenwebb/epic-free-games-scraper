import json
import os
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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
        files = {"attachment": open(image_path, "rb")} if image_path else None

        response = requests.post("https://api.pushover.net/1/messages.json", data=data, files=files)
        if response.status_code == 200:
            print("Pushover notification sent successfully.")
        else:
            print(f"Failed to send Pushover notification: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error sending Pushover notification: {e}")

def scrape_epic_free_games():
    # Load settings
    settings = load_settings()
    pushover_enabled = settings.get("pushover", {}).get("enabled", False)
    user_key = settings.get("pushover", {}).get("user_key", "")
    app_token = settings.get("pushover", {}).get("app_token", "")
    notify_always = settings.get("pushover", {}).get("notify_always", False)

    # Path to ChromeDriver
    driver_path = '/usr/bin/chromedriver'

    # Configure WebDriver options
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # Run in headless mode
    options.add_argument('--no-sandbox')  # Required for Docker
    options.add_argument('--disable-dev-shm-usage')  # Prevent resource issues
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    options.add_argument("window-size=1920,1080")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Initialize WebDriver
    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=options)

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
        # Navigate to the Epic Games free games page
        url = 'https://store.epicgames.com/en-US/free-games'
        driver.get(url)

        # Wait until current and next offer cards are loaded
        WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.XPATH, '//div[@data-component="VaultOfferCard"]'))
        )
        WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.XPATH, '//div[@data-component="FreeOfferCard"]'))
        )

        # Scrape current free games
        offer_cards = driver.find_elements(By.XPATH, '//div[@data-component="VaultOfferCard"]')
        print(f"Number of current offer cards found: {len(offer_cards)}")

        for card in offer_cards:
            game_name = card.find_element(By.CSS_SELECTOR, 'h6').text
            game_link = card.find_element(By.CSS_SELECTOR, 'a').get_attribute('href')
            if not game_link.startswith("http"):
                game_link = "https://store.epicgames.com" + game_link

            game_id = game_link.split('/')[-1]
            image_url = card.find_element(By.XPATH, './/img[@data-testid="picture-image"]').get_attribute('src')
            date_period = card.find_element(By.CSS_SELECTOR, 'p > span').text.replace("Free Now - ", "").strip()

            # Check for duplicates
            existing_game = next((game for game in past_games if game['Link'] == game_link), None)
            if not existing_game:
                new_games.append(game_name)

                # Save image
                image_filename = f"{game_id}.jpg"
                image_path = os.path.join('output/images', image_filename)
                response = requests.get(image_url)
                with open(image_path, 'wb') as img_file:
                    img_file.write(response.content)

                # Add to past games
                past_games.append({
                    'Name': game_name,
                    'Link': game_link,
                    'Image': image_path,
                    'Availability': date_period
                })
            else:
                image_path = existing_game.get('Image')

            # Track current games for notifications
            current_games.append({
                'Name': game_name,
                'Link': game_link,
                'Image': image_path,
                'Availability': date_period
            })

        # Scrape next free games
        next_offer_cards = driver.find_elements(By.XPATH, '//div[@data-component="FreeOfferCard"]')
        print(f"Number of next offer cards found: {len(next_offer_cards)}")

        next_game_counter = 1
        for card in next_offer_cards:
            game_name = card.find_element(By.CSS_SELECTOR, 'h6').text
            game_link = card.find_element(By.CSS_SELECTOR, 'a').get_attribute('href')
            if not game_link.startswith("http"):
                game_link = "https://store.epicgames.com" + game_link

            image_url = card.find_element(By.XPATH, './/img[@data-testid="picture-image"]').get_attribute('src')
            availability = card.find_element(By.CSS_SELECTOR, 'p > span').text.strip().replace("Free ", "")

            # Save image with dynamic filename
            image_filename = f"next-game{next_game_counter}.jpg"
            image_path = os.path.join('output/images', image_filename)
            response = requests.get(image_url)
            with open(image_path, 'wb') as img_file:
                img_file.write(response.content)

            existing_next_game_images.append(image_filename)
            next_game_counter += 1

            # Add to next games
            next_games.append({
                'Name': game_name,
                'Link': game_link,
                'Image': image_path,
                'Availability': availability
            })

        # Cleanup old next-game images
        for filename in os.listdir('output/images'):
            if filename.startswith("next-game") and filename not in existing_next_game_images:
                os.remove(os.path.join('output/images', filename))
                print(f"Removed unused file: {filename}")

        # Notify via Pushover
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

    finally:
        driver.quit()

if __name__ == '__main__':
    scrape_epic_free_games()
    
