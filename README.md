# Epic Games Scraper

A Python-based web scraper for fetching the weekly free games from the Epic Games Store. Includes Docker support for easy deployment.

It uses Selenium in a docker to load the page as the Free Game section is loaded using JavaScript, so basic scraping doesn't work.

## Features
- Scrapes free game titles, links, images, and availability dates.
- Saves data as a JSON file and downloads game images.

## Usage

1. Build the Docker image:
      docker build -t epic-games-scraper .
   
2. Run the scraper:
      docker run --rm -v "/path/to/output:/app/output" epic-games-scraper
