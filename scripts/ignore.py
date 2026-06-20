#!/usr/bin/env python3
# ============================================================================
# van-rental-search — IGNORE-LIST editor
# ============================================================================
# Append a listing the user is NOT interested in to config/ignored.json so the
# next bus_generate.py run (and the registry) drops it. Idempotent: re-adding an
# existing id just updates its note. Matches the data-bus item ids:
#   tel:<digits>   — preferred; collapses all reposts from one landlord
#   url:<listing>  — used when a listing has no phone
#
# Two ignore MODES:
#   HARD  (default)       — hide forever; the reason can't change (wrong bedroom
#                           count, low-info post, bad area).
#   PRICE (--until-below N)— hide only while the listing's current price is >= N.
#                           If the landlord later drops it below N it RE-SURFACES
#                           (flagged 降价回归). Use for "too expensive right now".
#
# Usage:
#   python3 scripts/ignore.py 604-555-1234 --reason "信息太少"        # HARD
#   python3 scripts/ignore.py 604-555-1234 --until-below 1800 --price 2000
#                                # PRICE: saw it at $2000, show again if it drops <$1800
#   python3 scripts/ignore.py "tel:6045551234"
#   python3 scripts/ignore.py "https://c.vanpeople.com/zufang/item-123.html"
#   python3 scripts/ignore.py --list            # show current ignore list
#   python3 scripts/ignore.py --remove 604-555-1234
# ============================================================================

import argparse
import json
import os
import sys
from datetime import date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from search import norm_phone  # noqa: E402

ROOT = os.path.dirname(SCRIPT_DIR)
IGNORED_PATH = os.path.join(ROOT, "config", "ignored.json")


def canonical_id(token):
    """Normalize a user-supplied token to a 'tel:'/'url:' id, or None."""
    t = (token or "").strip()
    if not t:
        return None
    if t.startswith(("tel:", "url:")):
        return t
    if t.startswith("http"):
        return "url:" + t
    p = norm_phone(t)
    return ("tel:" + p) if p else None


def load():
    try:
        with open(IGNORED_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return {"ignored": []}


def save(data):
    with open(IGNORED_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    ap = argparse.ArgumentParser(description="Edit the van-rental ignore list.")
    ap.add_argument("token", nargs="?", help="phone / url / tel:digits / url:...")
    ap.add_argument("--reason", default="", help="why you're not interested")
    ap.add_argument("--title", default="", help="optional listing title, for the record")
    ap.add_argument("--until-below", type=int, metavar="PRICE", dest="until_below",
                    help="PRICE-mode ignore: re-surface this listing only if its "
                         "price later drops below PRICE (for 'too expensive now')")
    ap.add_argument("--price", type=int, metavar="PRICE", dest="seen_price",
                    help="record the price you saw it at (display only)")
    ap.add_argument("--list", action="store_true", help="print the current ignore list")
    ap.add_argument("--remove", metavar="TOKEN", help="un-ignore a listing")
    args = ap.parse_args()

    data = load()
    data.setdefault("ignored", [])

    if args.list:
        if not data["ignored"]:
            print("(ignore list is empty)")
        for e in data["ignored"]:
            mode = (f"[降价回归<${e['untilBelowPrice']}]"
                    if e.get("untilBelowPrice") is not None else "[永久]")
            print(f"{e.get('id'):<20} {mode:<16} {e.get('title','')}  "
                  f"— {e.get('reason','')} ({e.get('addedAt','')})")
        return

    if args.remove:
        rid = canonical_id(args.remove)
        before = len(data["ignored"])
        data["ignored"] = [e for e in data["ignored"] if e.get("id") != rid]
        save(data)
        print(f"Removed {rid!r}" if len(data['ignored']) < before
              else f"{rid!r} was not in the list")
        return

    if not args.token:
        ap.error("provide a phone/url/id to ignore, or --list / --remove")
    iid = canonical_id(args.token)
    if not iid:
        ap.error(f"could not parse {args.token!r} into a phone or url")

    for e in data["ignored"]:  # idempotent: update note if already present
        if e.get("id") == iid:
            if args.reason:
                e["reason"] = args.reason
            if args.title:
                e["title"] = args.title
            if args.until_below is not None:
                e["untilBelowPrice"] = args.until_below
            if args.seen_price is not None:
                e["ignoredAtPrice"] = args.seen_price
            save(data)
            print(f"Already ignored {iid!r} — updated.")
            return

    entry = {
        "id": iid,
        "title": args.title,
        "reason": args.reason,
        "addedAt": date.today().isoformat(),
    }
    if args.until_below is not None:
        entry["untilBelowPrice"] = args.until_below
    if args.seen_price is not None:
        entry["ignoredAtPrice"] = args.seen_price
    data["ignored"].append(entry)
    save(data)
    mode = (f"hidden until price < ${args.until_below}"
            if args.until_below is not None else "hidden permanently")
    print(f"Ignored {iid!r} ({mode}). Takes effect next run.")


if __name__ == "__main__":
    main()
