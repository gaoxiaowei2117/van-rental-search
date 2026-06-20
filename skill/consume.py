#!/usr/bin/env python3
# ============================================================================
# van-rental-cloud — READ-ONLY consumer of the cloud rental snapshot
# ============================================================================
# Self-contained (pure Python stdlib, no pip installs, no repo checkout).
# Fetches the daily-refreshed bus/data.json published by the van-rental-search
# GitHub Actions job and prints it as Markdown or JSON.
#
# This reads a CURATED feed: the cities, price/floor filters and the personal
# ignore-list ("not interested" / 待考虑) all live on the producer side, so you
# get exactly the listings the owner curated — you do NOT scrape anything here.
#
# Usage:
#   python3 consume.py                 # Markdown digest of all current listings
#   python3 consume.py --new-only      # only listings flagged 🆕 (last freshDays)
#   python3 consume.py --json          # raw data.json (every field, for the agent)
#   python3 consume.py --out report.md # write the Markdown report to a file
#   REPO=owner/name python3 consume.py # point at a different published repo
# ============================================================================

import argparse
import json
import os
import sys
import time
import urllib.request

DEFAULT_REPO = "gaoxiaowei2117/van-rental-search"
BRANCH = "main"
FILE_PATH = "bus/data.json"


def fetch_data(repo, branch):
    """Fetch bus/data.json from a public repo via raw.githubusercontent.com."""
    repo = os.environ.get("REPO", repo)
    # Cache-bust so we never get a stale CDN copy right after a push.
    url = (f"https://raw.githubusercontent.com/{repo}/{branch}/{FILE_PATH}"
           f"?t={int(time.time())}")
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    try:
        raw = urllib.request.urlopen(req, timeout=30).read()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Could not fetch {FILE_PATH}: {e}\nTried: {url}")
    return json.loads(raw.decode("utf-8"))


def price_cell(it):
    """Rent column; show before→after when a 待考虑 listing returned on a price change."""
    pr = it.get("priceReturn")
    if pr and pr.get("snapshotPrice") is not None and pr.get("currentPrice") is not None:
        old, new = pr["snapshotPrice"], pr["currentPrice"]
        arrow = "🔻" if new < old else "🔺"
        return f"${old} → ${new} {arrow}"
    return f"${it['price']}" if it.get("price") is not None else "—"


def to_markdown(data, new_only):
    items = [it for it in data["items"] if it["new"]] if new_only else data["items"]
    fd = data.get("freshDays")
    head = (f"新房源（最近{fd}天）" if fd else "新房源") if new_only else "全部房源"
    L = [f"# Vancouver 租房汇总 · {head}",
         "",
         f"> 生成：{data['generatedAt']} ｜ 共 {data['count']} 套"
         f"（其中新 {data['newCount']} 套"
         + (f"，已过滤脏价格 {data['droppedDirty']} 套" if data.get('droppedDirty') else "")
         + (f"，🔄{data['priceReturns']} 套价格变动待考虑" if data.get('priceReturns') else "")
         + "）",
         "> 查询：" + "、".join(
             f"{q['label']}({q['count']})" for q in data.get("queries", [])),
         ""]
    if data.get("errors"):
        L.append(f"> ⚠️ 查询错误：{data['errors']}")
        L.append("")
    L.append("| 新 | 租金 | 楼层 | 房源 | 电话 | 来源 | 链接 |")
    L.append("|---|---|---|---|---|---|---|")
    for it in items:
        rep = f" ×{it['reposts']}" if it.get("reposts", 1) > 1 else ""
        links = " ".join(f"[{i+1}]({u})" for i, u in enumerate(it["links"][:6]))
        flag = "🔄" if it.get("priceReturn") else ("🆕" if it["new"] else "")
        L.append(f"| {flag} | {price_cell(it)} | {it['floorLabel']} "
                 f"| {it['title'][:34]}{rep} | {it['tel'] or '—'} | {it['src']} | {links} |")
    L.append("")
    L.append(f"*共 {len(items)} 套。价格为房东标注，以洽谈为准。*")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--branch", default=BRANCH)
    ap.add_argument("--json", action="store_true", help="print raw data.json")
    ap.add_argument("--new-only", action="store_true", help="only new listings")
    ap.add_argument("--out", help="write Markdown report to this file")
    args = ap.parse_args()

    data = fetch_data(args.repo, args.branch)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    md = to_markdown(data, args.new_only)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md + "\n")
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(md)


if __name__ == "__main__":
    main()
