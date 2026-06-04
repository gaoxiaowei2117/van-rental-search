# van-rental-search

A [Claude Code](https://claude.com/claude-code) **Agent Skill** that searches
the two main Vancouver Chinese-classifieds — **vanpeople** (`c.vanpeople.com/zufang`)
and **vansky** (`vansky.com/info` 出租版) — for rental listings, filters them by
the sites' *real* fields, de-duplicates landlords who repost, and emits a clean
report (table or detailed contact list), optionally opening hits in Chrome.

The sites' own dropdown filters are AJAX/JS and don't work via plain URLs, so this
skill calls the real endpoints (vanpeople's `/ajax/pc/list.html`) and parses the
structured results directly — filtering is exact, not best-effort scraping.

## Features

- **Real site filters**: city, bedrooms, price range, rent type (整租/分租),
  house type (公寓/独立屋/连排屋/后巷屋), rent-includes (水/电/网/气),
  facilities (独立卫浴/厨房/家具/空调/车位…), pets (猫/狗).
- **Freshness & move-in**: `--posted-since N` days; `--available-from/--available-to`
  reads each detail page's 起租时间 / 最短租期.
- **Above-ground vs basement** classification (全地上 / 半地下) from listing text.
- **De-dup by phone** — collapses repost spam to one row with `×N` + all links.
- **Junk filter** — drops room-share / short-term posts mislabeled as 整租.
- **Outputs**: Markdown table, or `--contacts` detailed list (联系人 / 电话 /
  邮箱 / 微信 / 链接); `--out` to a file; `--open` in Chrome.

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
