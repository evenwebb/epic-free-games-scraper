# Epic Games Free Game Scraper With Notifications

A Python-based web scraper that fetches the weekly free games from the Epic Games Store. The scraper supports Docker for easy deployment and maintains a full history of past free games. Additionally, it provides information about upcoming games.

It uses Selenium in a Docker container to load the page as the Free Game section is loaded using JavaScript, so basic scraping doesn't work. User-agent spoofing is used otherwise the page won't load correctly.

---

## Features

### Scraping Features
- **Past Games**:
  - Scrapes all currently free games from the Epic Games Store.
  - Appends new games to the `Past Games` section in a JSON file while keeping historical data intact.
  - Avoids duplicate entries to maintain clean data.
- **Upcoming Games**:
  - Scrapes the next free games (from `FreeOfferCard` elements).
  - Replaces the `Next Games` section in the JSON file with every script run.
  - Dynamically names game images (e.g., `next-game.jpg`, `next-game2.jpg`).
  - Cleans up unused "next game" images after each run.

### Notifications
- **Pushover Notifications**:
  - Optionally sends notifications when new free games are detected.
  - Includes game availability and the game image in the notification.
  - Configurable settings:
    - `enabled`: Turn notifications on or off.
    - `notify_always`: Always notify or only notify for new games.

### JSON Output
The scraped data is saved in a structured JSON format:
- **Next Games**: Lists upcoming free games.
- **Past Games**: Maintains a complete history of all past and current free games.

```json
{
  "Next Games": [
    {
      "Name": "Upcoming Game 1",
      "Link": "https://store.epicgames.com/en-US/p/upcoming-game-1",
      "Image": "https://cdn.example.com/image1.jpg",
      "Availability": "Coming Soon"
    }
  ],
  "Past Games": [
    {
      "Name": "Past Game 1",
      "Link": "https://store.epicgames.com/en-US/p/past-game-1",
      "Image": "output/images/past-game-1.jpg",
      "Availability": "Jan 09 at 04:00 PM"
    },
    {
      "Name": "Past Game 2",
      "Link": "https://store.epicgames.com/en-US/p/past-game-2",
      "Image": "output/images/past-game-2.jpg",
      "Availability": "Jan 16 at 04:00 PM"
    }
  ]
}
