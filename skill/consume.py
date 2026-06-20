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
#   python3 consume.py --html feed.html --open   # clickable page, opened in browser
#   REPO=owner/name python3 consume.py # point at a different published repo
#
# Every listing carries its detail-page URL. In Markdown the listing TITLE is a
# clickable link; --html renders a page of clickable cards for one-tap opening.
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
    L.append("| 新 | 租金 | 楼层 | 房源（点标题看详情） | 电话 | 来源 | 更多 |")
    L.append("|---|---|---|---|---|---|---|")
    for it in items:
        rep = f" ×{it['reposts']}" if it.get("reposts", 1) > 1 else ""
        urls = [u for u in it.get("links", []) if u]
        title = (it.get("title") or "")[:40].replace("|", "/")
        # The title itself is the clickable detail link; extra reposts get [2][3]…
        title_cell = f"[{title}]({urls[0]})" if urls else (title or "—")
        more = (" ".join(f"[{i+1}]({u})" for i, u in enumerate(urls[:6]))
                if len(urls) > 1 else "—")
        flag = "🔄" if it.get("priceReturn") else ("🆕" if it["new"] else "")
        L.append(f"| {flag} | {price_cell(it)} | {it['floorLabel']} "
                 f"| {title_cell}{rep} | {it['tel'] or '—'} | {it['src']} | {more} |")
    L.append("")
    L.append(f"*共 {len(items)} 套。点房源标题打开详情页。价格为房东标注，以洽谈为准。*")
    return "\n".join(L)


def to_html(data, new_only):
    """A standalone, styled page where every listing is a clickable card —
    the most 'just click it' way to open detail pages from any browser."""
    import html as _html
    items = [it for it in data["items"] if it["new"]] if new_only else data["items"]
    head = "新房源" if new_only else "全部房源"
    cards = []
    for it in items:
        urls = [u for u in it.get("links", []) if u]
        href = urls[0] if urls else ""
        title = _html.escape(it.get("title") or "(无标题)")
        rep = f" ×{it['reposts']}" if it.get("reposts", 1) > 1 else ""
        tag = ("🔄 待考虑回归" if it.get("priceReturn")
               else ("🆕 新" if it.get("new") else ""))
        extra = "".join(
            f' <a href="{_html.escape(u)}" target="_blank" rel="noopener">[{i+1}]</a>'
            for i, u in enumerate(urls[:8])) if len(urls) > 1 else ""
        title_html = (f'<a href="{_html.escape(href)}" target="_blank" '
                      f'rel="noopener">{title}</a>') if href else title
        cards.append(
            f'<div class="card"><div class="meta"><span class="price">'
            f'{_html.escape(price_cell(it))}</span>'
            f'<span class="floor">{_html.escape(it.get("floorLabel",""))}</span>'
            f'<span class="tag">{tag}</span></div>'
            f'<div class="title">{title_html}{rep}</div>'
            f'<div class="sub">{_html.escape(it.get("area","") or "")} ｜ '
            f'{_html.escape(it.get("tel","") or "—")} ｜ {_html.escape(it.get("src",""))} ｜ '
            f'{_html.escape(it.get("date","") or "")}{extra}</div></div>')
    return (
        "<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Vancouver 租房 · {head}</title><style>"
        "body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;"
        "background:#f5f5f7;color:#1d1d1f;padding:16px}"
        "h1{font-size:20px}.card{background:#fff;border-radius:12px;padding:14px 16px;"
        "margin:10px 0;box-shadow:0 1px 3px rgba(0,0,0,.08)}"
        ".meta{display:flex;gap:10px;align-items:center;font-size:13px;color:#666}"
        ".price{font-size:18px;font-weight:700;color:#0a7d2c}"
        ".tag{margin-left:auto;color:#b25000}"
        ".title{font-size:16px;margin:6px 0 4px}.title a{color:#0066cc;text-decoration:none}"
        ".title a:hover{text-decoration:underline}.sub{font-size:13px;color:#888}"
        ".sub a{color:#0066cc;margin-left:4px}</style></head><body>"
        f"<h1>Vancouver 租房汇总 · {head}（{len(items)} 套）</h1>"
        f"<p style='color:#888;font-size:13px'>生成：{_html.escape(data.get('generatedAt',''))}"
        f" ｜ 点房源标题打开详情页</p>" + "".join(cards) + "</body></html>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--branch", default=BRANCH)
    ap.add_argument("--json", action="store_true", help="print raw data.json")
    ap.add_argument("--new-only", action="store_true", help="only new listings")
    ap.add_argument("--out", help="write Markdown report to this file")
    ap.add_argument("--html", nargs="?", const="van-rentals.html", metavar="FILE",
                    help="write a clickable HTML page (default van-rentals.html)")
    ap.add_argument("--open", action="store_true", dest="open_browser",
                    help="open the --html page in the default browser")
    args = ap.parse_args()

    data = fetch_data(args.repo, args.branch)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if args.html or args.open_browser:
        path = os.path.abspath(args.html or "van-rentals.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(to_html(data, args.new_only))
        print(f"Wrote {path}", file=sys.stderr)
        if args.open_browser:
            import webbrowser
            webbrowser.open("file://" + path)  # no-op-safe on headless agents
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
