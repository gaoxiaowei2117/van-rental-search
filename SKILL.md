---
name: van-rental-search
description: Search Vancouver-area Chinese classifieds (vanpeople.com + vansky.com) for rental listings filtered by city, bedroom count, price ceiling and rent type. Classifies each as above-ground vs basement (全地上/半地下), de-duplicates landlords who repost, outputs a Markdown report, and can open hits in Chrome. Use when the user wants to find 租房/房源 on vanpeople or vansky — e.g. "找 Burnaby 1800以下的两室", "search vanpeople for Richmond 2-bedroom under 2000", "本拿比全地上两室", "在vansky/vanpeople里查租房".
---

# Vancouver Rental Search (vanpeople + vansky)

Finds rental listings on the two main Vancouver Chinese classifieds and filters
them properly — the sites' own dropdown filters are AJAX/JS and don't work via
plain URLs, so this skill calls the real endpoints and parses results.

## When to use

Any request to find rentals on **vanpeople** (`c.vanpeople.com/zufang`) or
**vansky** (`vansky.com/info` 出租版) by city / bedrooms / price / floor.
Common phrasings: "找 Burnaby 1800 以下的两室", "全地上两室", "Richmond 2-bedroom
under 2000 on vanpeople", "把不重复的在 Chrome 打开".

## Quick start

```bash
python3 ~/.claude/skills/van-rental-search/scripts/search.py \
  --city Burnaby --bedrooms 2 --max-price 1800 --above-ground
```

Save to a file and open the above-ground hits in Chrome:

```bash
python3 ~/.claude/skills/van-rental-search/scripts/search.py \
  --city Burnaby --bedrooms 2 --max-price 1800 --above-ground \
  --out ~/workspace/zhaofang/burnaby-2br.md --open
```

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--city` | Burnaby | 城市名 (Burnaby, Richmond, Vancouver, Coquitlam, Surrey, New West, North Vancouver, …) |
| `--bedrooms` | 2 | 卧室数 1–5 |
| `--max-price` | 1800 | 月租上限 |
| `--min-price` | 1 | 月租下限 |
| `--rent-type` | 整租 | `整租` / `分租` / `any` |
| `--house-type` | — | 房屋类型(逗号分隔)：公寓,独立屋,连排屋,后巷屋 |
| `--rent-includes` | — | 租金须包含：水费,电费,网络,天然气 |
| `--facilities` | — | 须具备设施：洗衣,独立厨房,基本电器,基本家具,中央空调,独立卫浴,独立车位,充电桩 |
| `--pets` | — | 可养宠物：猫,狗 |
| `--posted-since` | 0 | 只看最近 N 天内发布/更新（列表数据自带，便宜） |
| `--available-from` | — | 起租时间不早于 YYYY-MM-DD（需抓详情页） |
| `--available-to` | — | 起租时间不晚于 YYYY-MM-DD（需抓详情页） |
| `--show-available` | off | 抓详情页补充每套的起租时间 / 最短租期 |
| `--above-ground` | off | 只保留全地上（**文字判断，非站点筛选项**；排除半地下/地下室） |
| `--source` | vanpeople | `vanpeople` / `vansky` / `both` |
| `--pages` | 6 | 每个来源抓取的列表页数（按发帖时间倒序，越大越全越慢） |
| `--contacts` | off | 详细清单格式：每套含联系人/电话/邮箱/微信/链接 |
| `--out` | — | 写入 .md 文件；不填则打印 |
| `--html` | off | 另存排版好的 .html（链接可点）并在 Chrome 打开 |
| `--open` | off | 在 Chrome 打开所有去重后的地上房源 |

## Real site filter fields (use these, don't invent)

These are vanpeople's actual filter dropdowns (scraped from the live UI).
Only `--above-ground` is a synthetic, text-based classification — everything
else maps to a genuine `vals[pid]` server filter:

| 维度 (pid) | 选项 |
|---|---|
| 房屋类型 (32) | 公寓 / 独立屋 / 连排屋 / 后巷屋 |
| 出租形式 (39) | 整租 / 分租 |
| 月租价格 (price) | 区间 |
| 卧室数量 (55) | 1–5 卧+ |
| 租金包含 (43) | 水费 / 电费 / 网络 / 天然气 |
| 设备设施 (48) | 洗衣设施 / 独立厨房 / 基本电器 / 基本家具 / 中央空调 / 独立卫浴 / 独立车位 / 充电桩 |
| 其他条件 (214) | 可养猫 / 可养狗 |
| 城市 (s_city) | Burnaby / Richmond / Vancouver / … |

When the user wants to "set filters first", offer these fields. Multi-select
groups accept comma-separated values.

Two more conditions come from the data rather than a dropdown:
- **发布时间** — each listing's posttime/lastupdate is in the list payload, so
  `--posted-since N` filters by freshness with no extra requests.
- **起租时间 / 入住时间** — only on the detail page (`起租时间: YYYY-MM-DD`,
  `最短租期: …`). `--available-from/--available-to/--show-available` fetch the
  (already-filtered, de-duped) detail pages to read it.

## How it works / notes for the agent

- **vanpeople is primary & fast**: it POSTs to `/ajax/pc/list.html` with
  `vals[55]`=bedroom, `vals[39]`=rent-type, `vals[price]`=min,max, `s_city`=city id.
  Results carry structured `showtags` like `['本拿比','独立屋','整租','2卧','1卫']`,
  so filtering is exact.
- **vansky is secondary & slow**: its GET filters are ignored server-side, so the
  skill crawls list pages (40/listing each, ~34 pages total) and fetches each
  candidate's detail page for rent/floor. Use `--source both` only when the user
  wants maximum coverage; it adds a minute or two.
- **Floor classification** comes from the title + description text
  (半地下/地下室/basement → ❌; 平地/地面/楼上/地上/高层 → ✅; otherwise ❓未注明).
  `半地上` counts as above-ground.
- **De-dup is by phone number** — many landlords repost the same unit dozens of
  times; the report collapses them to one row with `×N` and keeps all links.
- **Room-share / short-term junk** that mislabels itself as 整租 (找室友, 分租,
  单间, 短租, …) is filtered out automatically when `--rent-type 整租`.
- Prices are landlord-stated ("…左右"); always present them as approximate.
- After running, summarize the ✅ above-ground hits for the user and offer to
  `--open` them or save with `--out`. Mention the `×N` repost groups.

## Extending

City / bedroom / rent-type id maps live at the top of `scripts/search.py`
(`VP_CITY`, `VP_ROOMS`, `VP_RENTTYPE`). If vanpeople changes its filter ids,
re-scrape them from the `option_item` / `child_li` elements on
`https://c.vanpeople.com/zufang/`.
