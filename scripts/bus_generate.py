#!/usr/bin/env python3
# ============================================================================
# van-rental-search — Data-Bus PRODUCER (runs in GitHub Actions, daily cron)
# ============================================================================
# Pattern: git-as-a-data-bus (see data-bus-template).
#   1. Run run_search() for every query in config/bus_queries.json.
#   2. Merge + de-dup across queries by phone; flag each item new vs stale by
#      its own post/update date (within `fresh_days`).
#   3. Sanity-check the result, then write bus/data.json (full snapshot). The
#      workflow git-pushes it back.
#
# SILENT-FAILURE GUARD: scraping a third-party site means a layout/field change
# can make every query return nothing. Rather than overwrite a good snapshot
# with an empty one, we ABORT (leave bus/data.json untouched) and exit non-zero
# when the result is empty or collapses far below the previous run — so the
# Actions job goes red and you get an email instead of silently rotting data.
#
# The consumer (bus_consume.py, or any local skill) reads bus/data.json.
# Pure stdlib + the existing search.py engine — no third-party deps.
#
# Usage: python3 scripts/bus_generate.py
# ============================================================================

import json
import os
import sys
from datetime import datetime, timezone

# Make the search.py engine importable (same dir as this file).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from search import run_search, norm_phone  # noqa: E402

ROOT = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(ROOT, "config", "bus_queries.json")
DATA_PATH = os.path.join(ROOT, "bus", "data.json")

FLOOR_LABEL = {"above": "✅地上", "unknown": "❓未注明", "basement": "❌半地下"}

# If a run produces fewer than this fraction of the PREVIOUS run's listing
# count, treat it as a likely site breakage and abort instead of overwriting.
DEFAULT_SANITY_MIN_RATIO = 0.3

# Which run_search() params we accept from a query entry (with defaults).
QUERY_DEFAULTS = {
    "city": "Burnaby", "bedrooms": 2, "max_price": 1800, "min_price": 1,
    "rent_type": "整租", "source": "both", "pages": 6, "above_ground": False,
    "house_type": "", "rent_includes": "", "facilities": "", "pets": "",
    "posted_since": 0, "available_from": "", "available_to": "",
    "show_available": False,
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def listing_ts(row):
    """Best-effort post/update unix timestamp for a listing.
    Prefer the numeric `ts` (vanpeople lastupdate / vansky update); fall back to
    parsing the `date` string (YYYY-MM-DD). Returns 0 if unknown."""
    ts = row.get("ts") or 0
    if ts:
        return int(ts)
    d = row.get("date") or ""
    try:
        return int(datetime.fromisoformat(d)
                   .replace(tzinfo=timezone.utc).timestamp())
    except (ValueError, TypeError):
        return 0


def previous_count():
    """Listing count from the existing bus/data.json, or None if unavailable.
    Used by the sanity guard to detect a collapse vs the last good snapshot."""
    try:
        with open(DATA_PATH, encoding="utf-8") as f:
            return json.load(f).get("count")
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return None


def item_id(row):
    """Stable unique id for cross-query dedup: normalized phone, else the url."""
    p = norm_phone(row.get("tel", ""))
    return ("tel:" + p) if p else ("url:" + (row.get("url") or ""))


def to_item(row, labels, is_new):
    return {
        "id": item_id(row),
        "new": is_new,
        "title": row.get("title", ""),
        "price": row.get("price"),
        "floor": row.get("floor", "unknown"),
        "floorLabel": FLOOR_LABEL.get(row.get("floor", "unknown"), ""),
        "area": row.get("area") or "",
        "tel": row.get("tel") or "",
        "tel2": row.get("tel2") or "",
        "name": row.get("name") or "",
        "email": row.get("email") or "",
        "wechat": row.get("wechat") or "",
        "date": row.get("date") or "",
        "available": row.get("available") or "",
        "lease": row.get("lease") or "",
        "src": row.get("src", ""),
        "reposts": row.get("count", 1),
        "links": row.get("links", [row.get("url")] if row.get("url") else []),
        "matchedQueries": sorted(labels),
    }


def main():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    queries = config.get("queries", [])

    price_floor_default = config.get("min_plausible_price", 800)
    fresh_days = config.get("fresh_days", 3)
    sanity_min_ratio = config.get("sanity_min_ratio", DEFAULT_SANITY_MIN_RATIO)

    errors = []
    dropped_total = 0

    # 1. Run each query; collect rows tagged with their query label.
    merged = {}  # id -> {"row": row, "labels": set}
    query_summary = []
    for q in queries:
        label = q.get("label") or f"{q.get('city')} {q.get('bedrooms')}br"
        params = {k: q.get(k, d) for k, d in QUERY_DEFAULTS.items()}
        try:
            rows = run_search(**params)
        except Exception as e:  # noqa: BLE001 — one bad query shouldn't kill the run
            errors.append(f"{label}: {e}")
            query_summary.append({"label": label, "count": 0, "error": str(e)})
            continue
        # Data-cleaning: drop dirty/implausible prices (placeholder 电议 prices,
        # per-room prices from 分租 mislabeled as 整租). Never silently truncate —
        # the dropped count is logged and surfaced in the payload.
        floor = q.get("min_plausible_price", price_floor_default)
        kept = [r for r in rows if (r.get("price") or 0) >= floor]
        dropped = len(rows) - len(kept)
        dropped_total += dropped
        rows = kept
        query_summary.append({"label": label, "count": len(rows),
                              "droppedDirty": dropped})
        for r in rows:
            iid = item_id(r)
            if iid in merged:
                merged[iid]["labels"].add(label)
                # union the links from every query that matched this listing
                existing = merged[iid]["row"]
                existing.setdefault("links", [])
                for u in r.get("links", []):
                    if u not in existing["links"]:
                        existing["links"].append(u)
            else:
                merged[iid] = {"row": r, "labels": {label}}

    # 2. Flag "new" = posted/updated within the last `fresh_days` days, by the
    #    listing's OWN date (not by when we first saw it).
    ts = now_iso()
    fresh_cutoff = datetime.now(timezone.utc).timestamp() - fresh_days * 86400
    items = []
    new_count = 0
    for m in merged.values():
        is_new = listing_ts(m["row"]) >= fresh_cutoff
        if is_new:
            new_count += 1
        items.append(to_item(m["row"], m["labels"], is_new))

    # newest-flagged first, then above-ground, then by price
    order = {"above": 0, "unknown": 1, "basement": 2}
    items.sort(key=lambda it: (not it["new"], order.get(it["floor"], 1),
                               it["price"] if it["price"] is not None else 1e9))

    # 3. SANITY GUARD — refuse to overwrite a good snapshot with a broken one.
    prev = previous_count()
    abort = None
    if not items:
        abort = ("produced 0 listings — every query returned nothing "
                 "(vanpeople/vansky layout or fields likely changed)")
    elif prev and len(items) < prev * sanity_min_ratio:
        abort = (f"listing count collapsed {prev} -> {len(items)} "
                 f"(< {int(sanity_min_ratio * 100)}% of the previous run)")
    if abort:
        print(f"ABORT: {abort}. Keeping the previous bus/data.json untouched.",
              file=sys.stderr)
        if errors:
            print("Query errors: " + " | ".join(errors), file=sys.stderr)
        sys.exit(1)

    # 4. Write the public payload.
    payload = {
        "generatedAt": ts,
        "count": len(items),
        "newCount": new_count,
        "freshDays": fresh_days,
        "droppedDirty": dropped_total,
        "queries": query_summary,
        "errors": errors or None,
        "items": items,
    }
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote {len(items)} listing(s) ({new_count} new, "
          f"{dropped_total} dirty dropped) to bus/data.json"
          + (f" — {len(errors)} query error(s)" if errors else ""),
          file=sys.stderr)

    # Per-query errors are non-fatal to the snapshot (the healthy data is still
    # published above) but should still turn the run red so they're noticed.
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"Generation failed: {e}", file=sys.stderr)
        sys.exit(1)
