from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import requests
import time
import json

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

    try:
        # Navigate to the Epic Games free games page
        url = 'https://store.epicgames.com/en-US/free-games'
        driver.get(url)

        # Wait until the offer cards are loaded
        WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.XPATH, '//div[@data-component="VaultOfferCard"]'))
        )

        # Locate all elements with data-component="VaultOfferCard"
        offer_cards = driver.find_elements(By.XPATH, '//div[@data-component="VaultOfferCard"]')
        print(f"Number of offer cards found: {len(offer_cards)}")

        # Prepare to store scraped data
        scraped_data = []

        for card in offer_cards:
            try:
                # Extract game name
                game_name = card.find_element(By.CSS_SELECTOR, 'h6').text

                # Extract game link
                game_link_element = card.find_element(By.CSS_SELECTOR, 'a')
                game_link = game_link_element.get_attribute('href')
                if not game_link.startswith("http"):
                    game_link = "https://store.epicgames.com" + game_link

                # Extract image URL
                image_element = card.find_element(By.XPATH, './/img[@data-testid="picture-image"]')
                image_url = image_element.get_attribute('src')

                # Extract and clean availability period
                date_period_element = card.find_element(By.CSS_SELECTOR, 'p > span')
                date_period = date_period_element.text.replace("Free Now - ", "").strip()

                # Download the image
                image_filename = f"{game_name.replace(' ', '_')}.jpg"
                image_path = os.path.join('output/images', image_filename)
                os.makedirs('output/images', exist_ok=True)
                response = requests.get(image_url)
                with open(image_path, 'wb') as img_file:
                    img_file.write(response.content)

                # Store the data
                scraped_data.append({
                    'Name': game_name,
                    'Link': game_link,
                    'Image': image_path,
                    'Availability': date_period
                })

            except Exception as e:
                print(f"Error processing a card: {e}")

        # Save data to JSON
        json_file = 'output/free_games.json'
        os.makedirs('output', exist_ok=True)
        with open(json_file, 'w', encoding='utf-8') as file:
            json.dump(scraped_data, file, indent=4, ensure_ascii=False)

        print(f"Data scraped successfully. Saved to {json_file}")

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        driver.quit()

if __name__ == '__main__':
    scrape_epic_free_games()
    