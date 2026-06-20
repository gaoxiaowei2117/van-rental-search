# van-rental-cloud — openclaw skill (read-only Vancouver rental feed)

A self-contained skill for **openclaw** that reads a curated, daily-refreshed
Vancouver rental feed. It does **not** scrape any site and takes no search
parameters — it fetches the latest snapshot that the
[`van-rental-search`](https://github.com/gaoxiaowei2117/van-rental-search)
GitHub Actions cron publishes, and presents it.

## What's in this folder

| File | Purpose |
|---|---|
| `SKILL.md` | Skill definition — trigger phrases, how to run, how to read the output. |
| `consume.py` | Standalone fetcher/renderer. **Pure Python 3 stdlib — nothing to install.** |
| `README.md` | This file. |

These three files are the **entire** install. Nothing else from the
`van-rental-search` repo is needed (the engine, the producer, the configs and
the ignore-list all live on the producer side and are irrelevant here).

## Install

1. Copy this whole folder into openclaw's skills directory:

   ```bash
   cp -r van-rental-cloud  <openclaw-skills-dir>/
   ```

   The exact skills directory (and whether openclaw needs a reload/restart to
   pick up a new skill) follows openclaw's own conventions — check its docs.

2. **Frontmatter check.** `SKILL.md` uses Claude-Code-style YAML frontmatter
   (`name` + `description`). If openclaw expects different field names or a
   different header format, adjust those few lines — the body stays the same.

3. Verify it runs (no openclaw needed for this smoke test):

   ```bash
   python3 consume.py --new-only      # should print a Markdown table of listings
   ```

## Usage (what the skill runs)

```bash
python3 consume.py                # Markdown digest of ALL current listings
python3 consume.py --new-only     # only the 🆕 ones (last freshDays)
python3 consume.py --json         # raw JSON (every field) for filtering/sorting
python3 consume.py --out feed.md  # write the Markdown report to a file
REPO=owner/name python3 consume.py # read a different published repo
```

## Reading the output

Columns: `新 | 租金 | 楼层 | 房源 | 电话 | 来源 | 链接`.

- 🆕 — posted/updated within the feed's freshness window.
- 🔄 with a rent cell like `$2000 → $1850 🔻` — a 待考虑 ("reconsider") listing
  that returned because its price changed (before → after; 🔻 down / 🔺 up).
- 楼层: ✅地上 above-ground / ❓未注明 floor not stated. Basements are excluded.
- Prices are landlord-stated and approximate.

## What this skill can / can't do

| Can | Can't |
|---|---|
| Show the curated feed (Burnaby + Coquitlam, ≤$2000, above-ground, last 7 days, ignore-list applied) | Change cities / price / floor filters |
| All listings, new-only, or raw JSON | Mark a listing "not interested" |
| Surface 待考虑 price-change returns | Scrape vanpeople/vansky directly |

Changing the criteria or the ignore-list is a **producer-side** change in the
`van-rental-search` repo, not here.

## Updating

Nothing to update on a schedule — `consume.py` always fetches the latest
snapshot live. Re-copy this folder only if `consume.py` / `SKILL.md` themselves
change in the source repo (`dist/openclaw/van-rental-cloud/`).
