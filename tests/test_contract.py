#!/usr/bin/env python3
# ============================================================================
# Contract test — does vanpeople's list API still return the fields search.py
# depends on? Network-dependent BY DESIGN. Run it in CI before generating data
# so a site change fails loudly here instead of silently producing 0 listings.
#
#   python3 tests/test_contract.py     # exits 0 if the contract holds, 1 if not
#
# It probes the live endpoint with a broad Burnaby 2-bedroom query (which
# normally has plenty of listings) and asserts the shape search_vanpeople()
# hard-codes: data.list exists and its items carry id/url/showtags, the
# bedroom tag is still formatted "N卧", and phones are still reachable.
# ============================================================================

import json
import os
import sys
import urllib.parse

SCRIPT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPT_DIR)
from search import fetch, VP_API, VP_CITY, VP_ROOMS  # noqa: E402

# Keys search_vanpeople() indexes directly (it["id"], it["url"]) or filters on
# (showtags). If any of these is renamed, every result is silently dropped.
REQUIRED_ITEM_KEYS = {"id", "url", "showtags"}


def fail(msg):
    print(f"CONTRACT FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    body = {
        "vals[55]": VP_ROOMS[2],
        "vals[price]": "1,99999",
        "sortid": "42", "s_city": VP_CITY["burnaby"], "tagid": "0",
        "is_see_private_car": "0", "page": "1",
    }
    raw = fetch(VP_API, urllib.parse.urlencode(body).encode())
    if not raw:
        fail(f"empty response from {VP_API} (network down or endpoint moved)")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"response is not JSON ({e}); first 200 chars: {raw[:200]!r}")

    try:
        items = data["data"]["list"]
    except (KeyError, TypeError):
        fail(f"missing data.list — response shape changed; top-level keys: {list(data)[:8]}")

    if not items:
        fail("data.list is empty for Burnaby 2-bedroom — expected listings; "
             "filter params (vals[55]/s_city) may have changed meaning")

    first = items[0]
    missing = REQUIRED_ITEM_KEYS - set(first)
    if missing:
        fail(f"list item missing required keys {sorted(missing)}; got {sorted(first)[:20]}")

    if not any(isinstance(t, str) and "卧" in t
               for it in items for t in (it.get("showtags") or [])):
        fail("no showtag contains '卧' — bedroom tag format changed; "
             "search_vanpeople()'s `f\"{bedrooms}卧\"` filter would drop everything")

    if not any((it.get("tel") or it.get("telnum1")) for it in items):
        fail("no item carries tel/telnum1 — phone field changed; dedup-by-phone would break")

    print(f"CONTRACT OK: {len(items)} item(s); required keys present "
          f"({sorted(REQUIRED_ITEM_KEYS)}), 卧 tag + phone fields intact.")


if __name__ == "__main__":
    main()
