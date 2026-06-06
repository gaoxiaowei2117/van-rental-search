#!/usr/bin/env python3
# ============================================================================
# van-rental-search — Data-Bus CONSUMER (runs locally / from a skill)
# ============================================================================
# The "pull" half. The repo is PUBLIC, so we just fetch bus/data.json over
# plain HTTP from raw.githubusercontent.com — no clone, no auth, no token.
#
# Usage:
#   python3 scripts/bus_consume.py                 # print a digest to stdout
#   python3 scripts/bus_consume.py --json          # print raw data.json
#   python3 scripts/bus_consume.py --new-only      # only items flagged new
#   python3 scripts/bus_consume.py --out report.md # write a Markdown report
#   REPO=owner/name python3 scripts/bus_consume.py # override target repo
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


def to_markdown(data, new_only):
    items = [it for it in data["items"] if it["new"]] if new_only else data["items"]
    head = "新房源" if new_only else "全部房源"
    L = [f"# Vancouver 租房汇总 · {head}",
         "",
         f"> 生成：{data['generatedAt']} ｜ 共 {data['count']} 套"
         f"（其中新 {data['newCount']} 套）",
         f"> 查询：" + "、".join(
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
        flag = "🆕" if it["new"] else ""
        L.append(f"| {flag} | ${it['price']} | {it['floorLabel']} "
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
