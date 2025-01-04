import json
import os
import requests
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def scrape_epic_free_games():
    # Path to ChromeDriver
    driver_path = '/usr/bin/chromedriver'

    # Configure WebDriver options
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # Run in headless mode
    options.add_argument('--no-sandbox')  # Required for Docker
    options.add_argument('--disable-dev-shm-usage')  # Prevent resource issues
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")  # Custom user agent
    options.add_argument("window-size=1920,1080")  # Set window size
    options.add_experimental_option("excludeSwitches", ["enable-automation"])  # Disable WebDriver detection
    options.add_experimental_option("useAutomationExtension", False)

    # Initialize WebDriver using Service
    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=options)

    # Path to the JSON file
    json_file = 'output/free_games.json'
    os.makedirs('output', exist_ok=True)

    # Load existing data from the JSON file
    if os.path.exists(json_file):
        with open(json_file, 'r', encoding='utf-8') as file:
            scraped_data = json.load(file)
    else:
        scraped_data = []

    try:
        # Navigate to the Epic Games free games page
        url = 'https://store.epicgames.com/en-US/free-games'
        driver.get(url)

        # Wait until both current and next offer cards are loaded
        WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.XPATH, '//div[@data-component="VaultOfferCard"]'))
        )
        WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.XPATH, '//div[@data-component="FreeOfferCard"]'))
        )

        # Scrape current free games
        offer_cards = driver.find_elements(By.XPATH, '//div[@data-component="VaultOfferCard"]')
        print(f"Number of current offer cards found: {len(offer_cards)}")

        # Scrape next free games
        next_offer_cards = driver.find_elements(By.XPATH, '//div[@data-component="FreeOfferCard"]')
        print(f"Number of next offer cards found: {len(next_offer_cards)}")

        # Prepare data for current and next games
        current_games = []
        next_games = []

        # Process current free games
        for card in offer_cards:
            try:
                game_name = card.find_element(By.CSS_SELECTOR, 'h6').text
                game_link_element = card.find_element(By.CSS_SELECTOR, 'a')
                game_link = game_link_element.get_attribute('href')
                if not game_link.startswith("http"):
                    game_link = "https://store.epicgames.com" + game_link

                game_id = game_link.split('/')[-1]
                image_filename = f"{game_id}.jpg"
                image_path = os.path.join('output/images', image_filename)

                image_element = card.find_element(By.XPATH, './/img[@data-testid="picture-image"]')
                image_url = image_element.get_attribute('src')

                date_period_element = card.find_element(By.CSS_SELECTOR, 'p > span')
                date_period = date_period_element.text.replace("Free Now - ", "").strip()

                # Avoid duplicates
                if any(game['Link'] == game_link for game in scraped_data):
                    print(f"Game '{game_name}' is already in the data. Skipping.")
                    continue

                # Download the image
                os.makedirs('output/images', exist_ok=True)
                response = requests.get(image_url)
                with open(image_path, 'wb') as img_file:
                    img_file.write(response.content)

                # Add the game data
                current_games.append({
                    'Name': game_name,
                    'Link': game_link,
                    'Image': image_path,
                    'Availability': date_period
                })

            except Exception as e:
                print(f"Error processing a current offer card: {e}")

        # Process next free games
        for card in next_offer_cards:
            try:
                game_name = card.find_element(By.CSS_SELECTOR, 'h6').text
                game_link_element = card.find_element(By.CSS_SELECTOR, 'a')
                game_link = game_link_element.get_attribute('href')
                if not game_link.startswith("http"):
                    game_link = "https://store.epicgames.com" + game_link

                game_id = game_link.split('/')[-1]
                image_element = card.find_element(By.XPATH, './/img[@data-testid="picture-image"]')
                image_url = image_element.get_attribute('src')

                next_games.append({
                    'Name': game_name,
                    'Link': game_link,
                    'Image': image_url,
                    'Availability': "Coming Soon"
                })

            except Exception as e:
                print(f"Error processing a next offer card: {e}")

        # Update JSON data
        updated_data = {
            'Next Games': next_games,
            'Past Games': scraped_data + current_games
        }

        # Save updated data to JSON
        with open(json_file, 'w', encoding='utf-8') as file:
            json.dump(updated_data, file, indent=4, ensure_ascii=False)

        print(f"Data scraped successfully. Updated data saved to {json_file}")

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        driver.quit()

if __name__ == '__main__':
    scrape_epic_free_games()
