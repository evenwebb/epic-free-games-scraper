#!/usr/bin/env python3
"""
Compare current freeGamesPromotions JSON hash to output/.api_hash.
Used by GitHub Actions check-api job (stdlib only; no pip install).
Writes api_unchanged=true|false to GITHUB_OUTPUT when set.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import epic_config  # noqa: E402


def main() -> int:
    hash_file = os.path.join(_REPO_ROOT, "output", ".api_hash")
    req = urllib.request.Request(
        epic_config.FREE_GAMES_PROMOTIONS_URL,
        headers={"User-Agent": "epic-free-games-scraper-actions/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        print(f"HTTP error fetching API: {e.code} {e.reason}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Network error fetching API: {e.reason}", file=sys.stderr)
        return 1

    try:
        data = json.loads(raw.decode())
    except json.JSONDecodeError as e:
        print(f"Invalid JSON from API: {e}", file=sys.stderr)
        return 1

    current = hashlib.sha256(
        json.dumps(data, sort_keys=True).encode()
    ).hexdigest()
    prev = ""
    if os.path.isfile(hash_file):
        with open(hash_file, encoding="utf-8") as f:
            prev = f.read().strip()

    unchanged = bool(prev and current == prev)
    print(
        "✓ API unchanged - skipping scrape"
        if unchanged
        else "API changed - running full scrape"
    )

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"api_unchanged={'true' if unchanged else 'false'}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
