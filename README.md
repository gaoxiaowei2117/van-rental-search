# van-rental-search

A [Claude Code](https://claude.com/claude-code) **Agent Skill** that searches
the two main Vancouver Chinese-classifieds — **vanpeople** (`c.vanpeople.com/zufang`)
and **vansky** (`vansky.com/info` 出租版) — for rental listings, filters them by
the sites' *real* fields, de-duplicates landlords who repost, and emits a clean
report (table or detailed contact list), optionally opening hits in Chrome.

The sites' own dropdown filters are AJAX/JS and don't work via plain URLs, so this
skill calls the real endpoints (vanpeople's `/ajax/pc/list.html`) and parses the
structured results directly — filtering is exact, not best-effort scraping.

## Daily cloud sync (git-as-a-data-bus)

A GitHub Actions cron runs the engine daily in the cloud and commits the results
back into the repo, so a local skill can read them without scraping live:

```
  Actions (cron, UTC)              the repo (public)             local consumer
  scripts/bus_generate.py                                     scripts/bus_consume.py
       │  run_search() × queries        │                            │
       │ ── write bus/data.json ──────► │  (push: producer writes)   │
       │                                │ ◄── raw HTTP GET ───────── │  (pull)
```

- **Producer** (`scripts/bus_generate.py`): runs every query in
  `config/bus_queries.json`, merges + de-dups by phone across queries, and writes
  `bus/data.json` (full snapshot — each item flagged `"new": true/false` when its
  own post/update date is within `fresh_days`). Pure stdlib.
- **Silent-failure guard**: scraping a third-party site means a layout change can
  make every query return nothing. A `tests/test_contract.py` gate runs first and
  fails the job if vanpeople's response shape changed; the producer then refuses
  to overwrite a good snapshot with an empty/collapsed one (`sanity_min_ratio`)
  and exits non-zero — so a breakage turns the Actions run red (email) instead of
  rotting the data silently.
- **Consumer** (`scripts/bus_consume.py`): the repo is **public**, so it just
  fetches `bus/data.json` over plain HTTP from `raw.githubusercontent.com` — no
  clone, no auth. `--new-only` shows just the day's new listings; `--out
  report.md` writes Markdown; `--json` prints the raw payload.
- **Schedule**: `.github/workflows/update-rentals.yml`, daily at 13:23 UTC
  (≈ 05:23 Vancouver). Edit the cron there; edit the search criteria in
  `config/bus_queries.json`.

```bash
# locally, read the latest cloud-synced results:
python3 scripts/bus_consume.py --new-only          # just today's new listings
python3 scripts/bus_consume.py --out ~/rentals.md  # full snapshot to a file
```

## Features

- **Real site filters**: city, bedrooms, price range, rent type (整租/分租),
  house type (公寓/独立屋/连排屋/后巷屋), rent-includes (水/电/网/气),
  facilities (独立卫浴/厨房/家具/空调/车位…), pets (猫/狗).
- **Freshness & move-in**: `--posted-since N` days; `--available-from/--available-to`
  reads each detail page's 起租时间 / 最短租期.
- **Above-ground vs basement** classification (全地上 / 半地下) from listing text.
- **De-dup by phone** — collapses repost spam to one row with `×N` + all links.
- **Junk filter** — drops room-share / short-term posts mislabeled as 整租.
- **Outputs**: Markdown table, `--contacts` detailed list (联系人 / 电话 / 邮箱 /
  微信 / 链接), `--json` structured array, or `--html` styled clickable page;
  `--out` to a file; `--open`/`--html` open in the default browser (cross-platform).

## Use from any agent (not only Claude Code)

The engine has no framework lock-in:

- **CLI**: `python3 scripts/search.py ... --json`
- **Python**: `from search import run_search; run_search(city="Burnaby", bedrooms=2, ...)`
- **MCP**: `scripts/mcp_server.py` — a zero-dependency stdio MCP server exposing a
  `search_rentals` tool, usable by any MCP-capable agent (Claude, Cursor, open agents…).

  ```json
  { "mcpServers": { "van-rental-search":
      { "command": "python3", "args": ["/abs/path/scripts/mcp_server.py"] } } }
  ```

## Install

Clone into your Claude Code skills directory:

```bash
git clone <your-repo-url> ~/.claude/skills/van-rental-search
```

Claude Code auto-discovers it. Invoke by asking in plain language
("找 Burnaby 1800 以下的两室") or run the script directly.

## Usage

```bash
python3 scripts/search.py --city Burnaby --bedrooms 2 --max-price 1800 --above-ground

# detailed contact list of recent above-ground hits, saved + opened
python3 scripts/search.py --city Burnaby --bedrooms 2 --max-price 1800 \
  --posted-since 60 --above-ground --source both --contacts \
  --out burnaby.md
```

See [`SKILL.md`](SKILL.md) for the full option reference and field/id maps.

## Notes

- Prices are landlord-stated approximations.
- Requires Python 3 (standard library only) and, for `--open`, Google Chrome on macOS.
- If vanpeople changes its filter ids, re-scrape them from the `option_item` /
  `child_li` elements on `https://c.vanpeople.com/zufang/` (see SKILL.md → Extending).

## License

MIT
