"""Contract tests: Epic freeGamesPromotions JSON shape (no live API calls)."""

from __future__ import annotations

import json
from pathlib import Path

import epic_config
from epic_client import (
    compute_api_hash,
    epic_free_discount_percentage,
    extract_game_metadata,
    format_date,
    get_game_image_url,
    get_game_link,
    get_game_price,
    parse_offer_iso_dates,
    resolve_tag_names,
    sanitize_filename,
    validate_url,
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


def test_sanitize_filename():
    assert sanitize_filename("hello") == "hello"
    assert sanitize_filename("") == "unknown"
    assert sanitize_filename("../etc/passwd") == "_etc_passwd"
    assert sanitize_filename("test\x00null") == "test_null"
    assert sanitize_filename(".hidden") == "hidden"
    assert sanitize_filename("a" * 250) == "a" * 200


def test_resolve_tag_names():
    assert resolve_tag_names(None) is None
    assert resolve_tag_names("") is None
    assert resolve_tag_names("1395,1370") == "Action,Action-Adventure"
    assert resolve_tag_names("99999") == "99999"


def test_get_game_image_url():
    game = {"keyImages": [{"type": "Thumbnail", "url": "thumb.jpg"}, {"type": "OfferImageWide", "url": "wide.jpg"}]}
    assert get_game_image_url(game) == "wide.jpg"
    assert get_game_image_url({}) is None
    assert get_game_image_url({"keyImages": []}) is None


def test_get_game_price():
    game = {"price": {"totalPrice": {"originalPrice": 1999, "discountPrice": 0, "currencyCode": "GBP"}}}
    orig, disc, curr = get_game_price(game)
    assert orig == 1999
    assert disc == 0
    assert curr == "GBP"


def test_format_date():
    result = format_date("2026-08-15T16:00:00Z")
    assert "Aug 15" in result or "15 Aug" in result


def test_extract_game_metadata():
    game = {"title": "Test Game", "description": "A test", "namespace": "test", "isCodeRedemptionOnly": False}
    meta = extract_game_metadata(game)
    assert meta["description"] == "A test"
    assert meta["sandbox_id"] == "test"
    assert meta["is_code_redemption_only"] is False
    assert meta["is_blockchain_used"] is False


def test_validate_url():
    assert not validate_url("")
    assert not validate_url(None)
    assert not validate_url("http://example.com")
    assert not validate_url("ftp://example.com/file")
    assert validate_url("https://example.com/image.jpg")
