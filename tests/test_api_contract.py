"""Contract tests: Epic freeGamesPromotions JSON shape (no live API calls)."""

from __future__ import annotations

import json
from pathlib import Path

import epic_config
from scrape_epic_games import (
    compute_api_hash,
    epic_free_discount_percentage,
    get_game_link,
    parse_offer_iso_dates,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "free_games_promotions_sample.json"


def _load_fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def test_free_games_url_is_gb():
    assert "locale=en-GB" in epic_config.FREE_GAMES_PROMOTIONS_URL
    assert "country=GB" in epic_config.FREE_GAMES_PROMOTIONS_URL
    assert epic_config.STORE_PATH_LOCALE == "en-GB"


def test_catalog_elements_path():
    data = _load_fixture()
    games = data["data"]["Catalog"]["searchStore"]["elements"]
    assert isinstance(games, list)
    assert len(games) >= 2


def test_api_hash_deterministic():
    data = _load_fixture()
    a = compute_api_hash(data)
    b = compute_api_hash(data)
    assert a == b
    assert len(a) == 64


def test_get_game_link_locale_matches_config():
    data = _load_fixture()
    loc = epic_config.STORE_PATH_LOCALE
    g0 = data["data"]["Catalog"]["searchStore"]["elements"][0]
    assert get_game_link(g0) == f"https://store.epicgames.com/{loc}/p/fixture-current-game"
    g1 = data["data"]["Catalog"]["searchStore"]["elements"][1]
    assert get_game_link(g1) == f"https://store.epicgames.com/{loc}/p/fixture-upcoming-page"


def test_promotional_offer_fields():
    data = _load_fixture()
    game = data["data"]["Catalog"]["searchStore"]["elements"][0]
    offer = game["promotions"]["promotionalOffers"][0]["promotionalOffers"][0]
    assert epic_free_discount_percentage(offer) == 0
    start, end = parse_offer_iso_dates(offer, game["title"])
    assert start is not None and end is not None


def test_malformed_offer_safe():
    assert epic_free_discount_percentage({}) is None
    assert epic_free_discount_percentage({"discountSetting": {}}) is None
    assert parse_offer_iso_dates({}, "x") == (None, None)
