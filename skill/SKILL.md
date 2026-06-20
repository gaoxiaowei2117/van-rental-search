---
name: van-rental-cloud
description: Read the owner's curated Vancouver rental feed (Burnaby + Coquitlam, above-ground, last 7 days, with a personal "not interested" filter applied). Use when the user asks to see 房源 / 租房 / Vancouver rentals / 本拿比/高贵林的房子, "有什么新房源", "看看筛好的房源". Read-only: it fetches a daily-refreshed snapshot, it does NOT scrape any site or take search parameters.
---

# Vancouver Rental — Cloud Feed (read-only)

This skill reads a **curated, daily-refreshed** list of Vancouver rental listings
that a GitHub Actions cron produces. You do **not** scrape any website and you do
**not** choose cities or filters here — those live on the producer side. You just
fetch and present the latest snapshot.

Framework-agnostic: any AI agent that loads file-based skills (Claude Code,
openclaw, Cursor, …) can use it. The only requirement is `python3` on PATH.

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
python3 consume.py --html f.html --open   # clickable page of cards, opened in browser
```

Default behaviour: when the user asks "有什么房源 / 看看房源", run `python3 consume.py`
and show the table. If they say "有什么新的", add `--new-only`. If they want to
browse/open detail pages, run `--html … --open` (or just `--html …` on a headless
host and hand them the file path).

**Always keep the links clickable when you present results.** Every listing
carries its detail-page URL:
- In the Markdown table the **listing title is already a clickable link** to its
  detail page (extra reposts show as `[2] [3]…` in the 更多 column). Reproduce the
  table **verbatim** — do NOT strip the `[标题](url)` links or replace them with
  bare text, or the user loses the way to open the listing.
- If your surface does not render Markdown links, show the **full `https://…` URL**
  next to each listing instead, or generate the `--html` page and give the user
  the path. Never present a listing without a way to open it.

## Reading the output

Each row: `新 | 租金 | 楼层 | 房源（点标题看详情） | 电话 | 来源 | 更多`.
- 房源 = the **clickable title** → opens the listing's detail page. 更多 = links to
  the same landlord's other reposts (`[2] [3]…`), or `—` if there's only one.
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
