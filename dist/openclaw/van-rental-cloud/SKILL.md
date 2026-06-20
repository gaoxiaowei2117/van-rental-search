---
name: van-rental-cloud
description: Read the owner's curated Vancouver rental feed (Burnaby + Coquitlam, above-ground, last 7 days, with a personal "not interested" filter applied). Use when the user asks to see 房源 / 租房 / Vancouver rentals / 本拿比/高贵林的房子, "有什么新房源", "看看筛好的房源". Read-only: it fetches a daily-refreshed snapshot, it does NOT scrape any site or take search parameters.
---

# Vancouver Rental — Cloud Feed (read-only)

This skill reads a **curated, daily-refreshed** list of Vancouver rental listings
that another system (a GitHub Actions cron) produces. You do **not** scrape any
website and you do **not** choose cities or filters here — those live on the
producer side. You just fetch and present the latest snapshot.

What the feed already has baked in (do not re-explain as if configurable here):
- Cities: **Burnaby + Coquitlam**, 2-bedroom, ≤ $2000, **above-ground**, posted/updated in the **last 7 days**.
- De-duplicated by landlord phone (one row per unit, `×N` = repost count).
- A personal **ignore-list** is already applied: listings the owner marked
  "not interested" are removed; ones set aside as **待考虑** reappear (flagged 🔄)
  only when their price changes.

## How to run

Pure Python 3 stdlib — nothing to install.

```bash
python3 consume.py                # Markdown digest of ALL current listings
python3 consume.py --new-only     # only the 🆕 ones (posted in the last freshDays)
python3 consume.py --json         # raw JSON (every field) — use when the user wants
                                  # to filter/sort, or you need tel/links/priceReturn
python3 consume.py --out feed.md  # write the Markdown report to a file
```

Default behaviour: when the user asks "有什么房源 / 看看房源", run `python3 consume.py`
and show the table. If they say "有什么新的", add `--new-only`.

## Reading the output

Each row: `新 | 租金 | 楼层 | 房源 | 电话 | 来源 | 链接`.
- 🆕 = posted/updated within the feed's freshness window.
- 🔄 + a rent cell like `$2000 → $1850 🔻` = a 待考虑 listing that came back because
  its price changed (before → after, 🔻 down / 🔺 up). Call this out to the user.
- `楼层`: ✅地上 (above-ground) / ❓未注明 (floor not stated). The feed excludes basements.
- Prices are landlord-stated ("…左右") — always present them as approximate.

## Notes

- The data is read from a public URL, no auth/token needed. If the fetch fails,
  the snapshot URL or repo may have changed — tell the user; don't fabricate listings.
- To point at a different published repo: `REPO=owner/name python3 consume.py`.
- You **cannot** change the cities, price ceiling, or the ignore-list from here.
  If the user wants different criteria or to mark a listing "not interested",
  that's a change on the producer side (the van-rental-search repo) — tell them so.
