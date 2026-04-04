"""
Single source of truth for Epic Store API and storefront locale.

The GitHub Actions hash check and scrape_epic_games.py must both import from here
so the URL cannot drift.
"""

# IPv4 static endpoint (reliable from GitHub Actions; avoids IPv6-only issues).
FREE_GAMES_PROMOTIONS_URL = (
    "https://store-site-backend-static-ipv4.ak.epicgames.com/"
    "freeGamesPromotions?locale=en-GB&country=GB&allowCountries=GB"
)

# Product pages: align with API region (en-GB / GB).
STORE_PATH_LOCALE = "en-GB"

__all__ = ("FREE_GAMES_PROMOTIONS_URL", "STORE_PATH_LOCALE")
