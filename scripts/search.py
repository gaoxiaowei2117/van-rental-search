#!/usr/bin/env python3
"""
Vancouver Chinese-classifieds rental search.

Searches c.vanpeople.com (and optionally vansky.com) for rental listings
filtered by city, bedroom count, price ceiling and rent type, classifies
each as above-ground vs basement, de-duplicates by phone number, and emits
a Markdown report. Can also open the unique above-ground hits in Chrome.

Primary source is the vanpeople filter API (fast, structured). Vansky is an
optional secondary source that requires crawling list pages + detail pages.
"""
import argparse, json, os, re, sys, time, html, webbrowser, urllib.request, urllib.parse
from datetime import datetime, timezone


def open_in_browser(target):
    """Cross-platform: open a URL or local file in the default browser. No-op on failure (e.g. headless)."""
    url = target if re.match(r"^https?://", target) else "file://" + os.path.abspath(target)
    try:
        return webbrowser.open(url)
    except Exception:
        return False

# ---------- vanpeople constants (scraped from the live filter UI) ----------
VP_CITY = {
    "burnaby": "1", "coquitlam": "2", "new westminster": "3", "new west": "3",
    "richmond": "4", "vancouver": "5", "west vancouver": "6", "north vancouver": "7",
    "delta": "8", "langley": "9", "surrey": "10", "white rock": "11", "other": "12",
    "port coquitlam": "13", "port coq": "13", "maple ridge": "14", "abbotsford": "15",
    "whistler": "16", "port moody": "17", "victoria": "18", "pitt meadows": "19",
    "sunshine coast": "20", "nanaimo": "21",
}
VP_ROOMS = {1: "56", 2: "57", 3: "58", 4: "59", 5: "60"}   # data-id for "N卧+"
VP_RENTTYPE = {"整租": "42", "分租": "40", "whole": "42", "share": "40"}

# multi-select filter groups (real vanpeople fields) -> {alias: data-id}, with parent pid
VP_HOUSE = ("32", {"公寓": "35", "独立屋": "33", "连排屋": "34", "townhouse": "34",
                    "后巷屋": "36", "apartment": "35", "house": "33"})
VP_INCLUDE = ("43", {"水": "44", "水费": "44", "电": "316", "电费": "316",
                      "网": "45", "网络": "45", "气": "46", "天然气": "46"})
VP_FACIL = ("48", {"洗衣": "49", "洗衣设施": "49", "独立厨房": "50", "厨房": "50",
                    "基本电器": "52", "电器": "52", "基本家具": "51", "家具": "51",
                    "中央空调": "394", "空调": "394", "独立卫浴": "54", "卫浴": "54",
                    "独立车位": "53", "车位": "53", "充电桩": "395"})
VP_PET = ("214", {"可养猫": "392", "猫": "392", "可养狗": "393", "狗": "393"})
VP_API = "https://c.vanpeople.com/ajax/pc/list.html"


def map_multi(spec, raw):
    """raw='独立卫浴,家具' -> 'data-id1,data-id2' for the group's pid; returns (pid, joined) or None."""
    pid, table = spec
    if not raw:
        return None
    ids = []
    for tok in re.split(r"[，,/\s]+", raw.strip()):
        if tok and tok in table and table[tok] not in ids:
            ids.append(table[tok])
    return (pid, ",".join(ids)) if ids else None

# vansky display-name normalisation (its rows show English city names)
VANSKY_CITY = {
    "burnaby": "Burnaby", "richmond": "Richmond", "vancouver": "Vancouver",
    "surrey": "Surrey", "coquitlam": "Coquitlam", "new west": "New West",
    "north vancouver": "N. Vancouver", "west vancouver": "W. Vancouver",
    "delta": "Delta", "langley": "Langley", "port coquitlam": "Port Coq.",
    "port moody": "Port Moody",
}
VANSKY_LIST = "https://www.vansky.com/info/ZFBG08.html?page={}"
VANSKY_ITEM = "https://www.vansky.com/info/adfree/{}.html"

UA = {"User-Agent": "Mozilla/5.0"}

# room-share / short-term / non-home posts that mislabel themselves as 整租
SHARE_RE = re.compile(r"分租|合租|找室友|室友|单间|單間|单房|單房|主卧|主臥|次卧|次臥|其中一间|其中一間|一间房|一間房|间房间|間房間|招租女|招租男|短租|短期|车位|車位|停车位|停車位|仓库|倉庫")
BASEMENT_RE = re.compile(r"半地下|地下室|地庫|地库|地下|basement", re.I)
ABOVE_RE = re.compile(r"半地上|平地|地面|地麵|一层|一層|一楼|一樓|楼上|樓上|地上|高层|高層|中层|中層|顶层|頂層|楼层|樓層|主楼|主樓")


def classify_floor(text):
    if BASEMENT_RE.search(text):
        # "半地上" is above-ground despite containing neither — handled by ABOVE first
        return "basement"
    if ABOVE_RE.search(text):
        return "above"
    return "unknown"


def norm_phone(tel):
    d = re.sub(r"\D", "", tel or "")
    return d[-10:] if len(d) >= 10 else d


def fetch(url, data=None, tries=5):
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        except Exception:
            time.sleep(2)
    return ""


# ----------------------------- vanpeople -----------------------------
def search_vanpeople(city_id, bedrooms, max_price, min_price, rent_type, pages, extra_vals=None):
    out = {}
    for pg in range(1, pages + 1):
        body = {
            "vals[55]": VP_ROOMS.get(bedrooms, "57"),
            "vals[price]": f"{min_price},{max_price}",
            "sortid": "42", "s_city": city_id, "tagid": "0",
            "is_see_private_car": "0", "page": str(pg),
        }
        if rent_type in VP_RENTTYPE:
            body["vals[39]"] = VP_RENTTYPE[rent_type]
        for pid, joined in (extra_vals or {}).items():
            body[f"vals[{pid}]"] = joined
        raw = fetch(VP_API, urllib.parse.urlencode(body).encode(),)
        if not raw:
            continue
        try:
            items = json.loads(raw)["data"]["list"]
        except Exception:
            break
        if not items:
            break
        for it in items:
            out[it["id"]] = it
        time.sleep(0.2)

    rows = []
    for it in out.values():
        tags = it.get("showtags") or []
        if rent_type in ("整租", "whole") and "整租" not in tags:
            continue
        if rent_type in ("分租", "share") and "分租" not in tags:
            continue
        if f"{bedrooms}卧" not in tags:
            continue
        text = (it.get("title") or "") + " " + (it.get("intro") or "")
        if rent_type in ("整租", "whole") and SHARE_RE.search(text):
            continue
        price = int(re.sub(r"\D", "", str(it.get("price") or "0")) or 0)
        if not (min_price <= price <= max_price):
            continue
        upd = int(it.get("lastupdate") or it.get("posttime") or 0)
        post = int(it.get("posttime") or 0)
        floor = classify_floor(it.get("title", "") + " " + (it.get("intro") or ""))
        rows.append({
            "price": price, "floor": floor,
            "date": datetime.fromtimestamp(upd, timezone.utc).date().isoformat() if upd else "",
            "posted": datetime.fromtimestamp(post, timezone.utc).date().isoformat() if post else "",
            "ts": upd, "available": "", "lease": "",
            "tel": it.get("tel") or it.get("telnum1") or "", "tel2": it.get("tel2") or "",
            "name": (it.get("plus1") or "").strip(), "email": (it.get("email") or "").strip(),
            "wechat": (it.get("wechat") or "").strip(),
            "title": re.sub(r"\s+", " ", (it.get("title") or "")).strip(),
            "area": it.get("community") or it.get("areaname") or "",
            "url": "https://c.vanpeople.com" + it["url"], "src": "vanpeople",
        })
    return rows


def enrich_vanpeople_dates(rows):
    """Fetch each vanpeople detail page to fill 起租时间(available) + 最短租期(lease)."""
    for r in rows:
        if r.get("src") != "vanpeople":
            continue
        t = fetch(r["links"][0] if r.get("links") else r["url"])
        if not t:
            continue
        a = re.search(r"起租时间[:：]\s*(\d{4}-\d{2}-\d{2})", t)
        l = re.search(r"最短租期[:：]\s*([^<\n]{1,12})", t)
        r["available"] = a.group(1) if a else ""
        r["lease"] = html.unescape(l.group(1)).strip() if l else ""
        time.sleep(0.15)
    return rows


# ------------------------------ vansky -------------------------------
def _vansky_field(t, label):
    m = re.search(label + r"[：:]\s*</td>\s*<td[^>]*>(.*?)</td>", t, re.S)
    return html.unescape(re.sub("<[^>]+>", "", m.group(1))).strip() if m else ""


def search_vansky(city_name, bedrooms, max_price, min_price, rent_type, pages):
    disp = VANSKY_CITY.get(city_name.lower())
    if not disp:
        return []
    bed_kw = {1: ["1睡房", "一房", "一室"], 2: ["2睡房", "两室", "二房", "两房", "2室", "二室"],
              3: ["3睡房", "三房", "三室", "3室"], 4: ["4睡房", "四房"], 5: ["5睡房", "五房"]}.get(bedrooms, [])
    cand = {}
    for pg in range(1, pages + 1):
        t = fetch(VANSKY_LIST.format(pg))
        if not t:
            continue
        for seg in re.split(r'class="adsTitleFont" href="', t)[1:]:
            lm = re.match(r"(adfree/\d+\.html)", seg)
            if not lm:
                continue
            link = lm.group(1)
            tm = re.search(r'title="([^"]*)"', seg[:300])
            title = html.unescape(tm.group(1)).strip() if tm else ""
            dm = re.search(r'itemprop="description"[^>]*>(.*?)</div>', seg, re.S)
            desc = html.unescape(re.sub("<[^>]+>", "", dm.group(1))).strip() if dm else ""
            cm = re.search(r'class="adph-font">\s*<div>\s*([^<]+?)\s*</div>', seg, re.S)
            city = html.unescape(cm.group(1)).strip() if cm else ""
            if city != disp:
                continue
            if any(k in title + " " + desc for k in bed_kw):
                cand.setdefault(link, (title, desc))
        time.sleep(0.15)

    rows = []
    for link, (title, desc) in cand.items():
        iid = re.search(r"\d+", link).group(0)
        t = fetch(VANSKY_ITEM.format(iid))
        if not t:
            continue
        rent = _vansky_field(t, "租金或价格")
        way = _vansky_field(t, "出租方式")
        ftype = _vansky_field(t, "住宅类型")
        rooms = _vansky_field(t, "房间情况")
        if f"{bedrooms}睡房" not in rooms:
            continue
        if rent_type in ("整租", "whole") and "整租" not in way:
            continue
        m = re.search(r"(\d{3,5})", rent.replace(",", ""))
        price = int(m.group(1)) if m else 0
        if not price or not (min_price <= price <= max_price):
            continue
        ph = re.search(r"tel:([0-9][0-9\-]{6,})", t)
        floor = classify_floor(title + " " + desc + " " + ftype)
        avail = _vansky_field(t, "可用时间")
        am = re.search(r"\d{4}-\d{2}-\d{2}", avail)
        um = re.search(r"更新时间[:：]\s*(?:&nbsp;)?\s*(\d{4}-\d{2}-\d{2})", t)
        udate = um.group(1) if um else ""
        uts = int(datetime.strptime(udate, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()) if udate else 0
        nm = re.search(r"联系人[:：]\s*</span>\s*<span>([^<]+)</span>", t)
        em = re.search(r"mailto:([^\"?]+@[^\"?]+)", t)
        wc = re.search(r"微信\s*[:：]\s*(?:</[^>]+>\s*)?([A-Za-z0-9_\-]{3,})", t)
        rows.append({
            "price": price, "floor": floor, "date": udate, "posted": udate, "ts": uts,
            "available": am.group(0) if am else "", "lease": "",
            "tel": ph.group(1) if ph else "", "tel2": "",
            "name": html.unescape(nm.group(1)).strip() if nm else "",
            "email": em.group(1).strip() if em else "",
            "wechat": wc.group(1).strip() if wc else "",
            "title": re.sub(r"\s+", " ", title).strip(),
            "area": "", "url": VANSKY_ITEM.format(iid), "src": "vansky",
        })
        time.sleep(0.2)
    return rows


# ------------------------------ output -------------------------------
def dedupe(rows):
    by_phone = {}
    no_phone = []
    for r in rows:
        p = norm_phone(r["tel"])
        if not p:
            no_phone.append(r)
            continue
        if p not in by_phone:
            by_phone[p] = dict(r, links=[r["url"]], count=1)
        else:
            g = by_phone[p]
            g["count"] += 1
            g["links"].append(r["url"])
            g["price"] = min(g["price"], r["price"])
            if g["floor"] == "unknown" and r["floor"] != "unknown":
                g["floor"] = r["floor"]
            for k in ("name", "email", "wechat", "tel2", "available", "lease", "area"):
                if not g.get(k) and r.get(k):
                    g[k] = r[k]
    for r in no_phone:
        r["links"] = [r["url"]]
        r["count"] = 1
    return list(by_phone.values()) + no_phone


def to_markdown(rows, args):
    order = {"above": 0, "unknown": 1, "basement": 2}
    rows.sort(key=lambda r: (order.get(r["floor"], 1), r["price"]))
    above = [r for r in rows if r["floor"] in ("above", "unknown")]
    base = [r for r in rows if r["floor"] == "basement"]
    today = datetime.now().date().isoformat()
    L = [f"# {args.city} 租房 · {args.bedrooms}室 · ≤ ${args.max_price}",
         "", f"> 生成：{today} ｜ 条件：{args.city} · {args.bedrooms}卧 · {args.rent_type} · ≤${args.max_price}",
         f"> 来源：{args.source} ｜ 同一电话已去重（×N=重复发帖数）", ""]

    show_av = bool(args.available_from or args.available_to or args.show_available)
    av_h = " 起租 |" if show_av else ""
    av_sep = "---|" if show_av else ""

    def tbl(title, items):
        if not items:
            return
        L.append(f"## {title}")
        L.append("")
        L.append(f"| 租金 | 楼层 | 房源 | 发布 |{av_h} 电话 | 来源 | 链接 |")
        L.append(f"|---|---|---|---|{av_sep}---|---|---|")
        flabel = {"above": "✅地上", "unknown": "❓未注明", "basement": "❌半地下"}
        for r in items:
            rep = f" ×{r['count']}" if r["count"] > 1 else ""
            area = f" · {r['area']}" if r["area"] else ""
            links = " ".join(f"[{i+1}]({u})" for i, u in enumerate(r["links"][:6]))
            av = f" {r.get('available') or '—'}{(' ('+r['lease']+')') if r.get('lease') else ''} |" if show_av else ""
            L.append(f"| ${r['price']} | {flabel.get(r['floor'],'')} | {r['title'][:34]}{area}{rep} "
                     f"| {r.get('date') or '—'} |{av} {r['tel']} | {r['src']} | {links} |")
        L.append("")

    if args.above_ground:
        tbl("✅ 全地上", above)
    else:
        tbl("✅ 地上 / 未注明", above)
        tbl("❌ 半地下 / 地下室（参考）", base)
    L.append(f"*共 {len(above)} 套地上"
             + ("" if args.above_ground else f"，{len(base)} 套半地下") + "。价格为房东标注，以洽谈为准。*")
    return "\n".join(L)


def to_markdown_detailed(rows, args):
    order = {"above": 0, "unknown": 1, "basement": 2}
    rows.sort(key=lambda r: (order.get(r["floor"], 1), r["price"]))
    flabel = {"above": "✅ 全地上", "unknown": "❓ 楼层未注明", "basement": "❌ 半地下/地下室"}
    today = datetime.now().date().isoformat()
    L = [f"# {args.city} 租房详细清单 · {args.bedrooms}室 · ≤ ${args.max_price}",
         "", f"> 生成：{today} ｜ 条件：{args.city} · {args.bedrooms}卧 · {args.rent_type} · ≤${args.max_price}"
         + (f" · 最近{args.posted_since}天" if args.posted_since else "") + (" · 只要全地上" if args.above_ground else ""),
         f"> 来源：{args.source} ｜ 同一电话已去重 ｜ 共 {len(rows)} 套", ""]
    for i, r in enumerate(rows, 1):
        tels = " / ".join([x for x in [r.get("tel"), r.get("tel2")] if x]) or "（未提供，见网页）"
        L.append(f"## {i}. ${r['price']} · {flabel.get(r['floor'],'')} · {r['title']}")
        L.append("")
        L.append(f"- **联系人**：{r.get('name') or '—'}")
        L.append(f"- **电话**：{tels}")
        L.append(f"- **邮箱**：{r.get('email') or '—'}")
        L.append(f"- **微信**：{r.get('wechat') or '—'}")
        L.append(f"- **租金**：${r['price']}/月（房东标注，约数）")
        if r.get("area"):
            L.append(f"- **区域**：{r['area']}")
        if r.get("date"):
            L.append(f"- **更新/发布**：{r['date']}")
        if r.get("available") or r.get("lease"):
            L.append(f"- **起租时间**：{r.get('available') or '—'}" + (f" ｜ 最短租期：{r['lease']}" if r.get("lease") else ""))
        L.append(f"- **来源**：{r['src']}")
        if r.get("count", 1) > 1:
            L.append(f"- **同房东重复发帖**：{r['count']} 条")
        L.append("- **网页链接**：")
        for u in r.get("links", [r["url"]]):
            L.append(f"  - {u}")
        L.append("")
    return "\n".join(L)


def run_search(city="Burnaby", bedrooms=2, max_price=1800, min_price=1, rent_type="整租",
               house_type="", rent_includes="", facilities="", pets="",
               posted_since=0, available_from="", available_to="",
               show_available=False, above_ground=False, source="vanpeople", pages=6):
    """Core engine: returns the de-duplicated list of listing dicts. Framework-agnostic."""
    extra = {}
    for spec, raw in ((VP_HOUSE, house_type), (VP_INCLUDE, rent_includes),
                      (VP_FACIL, facilities), (VP_PET, pets)):
        m = map_multi(spec, raw)
        if m:
            extra[m[0]] = m[1]
    rows = []
    if source in ("vanpeople", "both"):
        cid = VP_CITY.get(city.lower())
        if cid is None:
            raise ValueError(f"未知城市 '{city}'，可选：{', '.join(sorted(VP_CITY))}")
        rows += search_vanpeople(cid, bedrooms, max_price, min_price, rent_type, pages, extra)
    if source in ("vansky", "both"):
        # vansky's ZFBG08 list is shallow per page and NOT strictly newest-first
        # (paid/置顶 ads occupy the early pages), so a brand-new free ad can land
        # deep in the list. Always crawl ≥30 pages — even under source="both",
        # where `pages` (tuned for vanpeople) would otherwise be far too few.
        rows += search_vansky(city, bedrooms, max_price, min_price, rent_type,
                              max(pages, 30))

    if posted_since > 0:
        cutoff = int(datetime.now(timezone.utc).timestamp()) - posted_since * 86400
        rows = [r for r in rows if r.get("ts", 0) >= cutoff]

    rows = dedupe(rows)
    if above_ground:
        rows = [r for r in rows if r["floor"] in ("above", "unknown")]

    if available_from or available_to or show_available:
        enrich_vanpeople_dates(rows)
        if available_from:
            rows = [r for r in rows if not r.get("available") or r["available"] >= available_from]
        if available_to:
            rows = [r for r in rows if not r.get("available") or r["available"] <= available_to]
    return rows


def render_html(md, title):
    """Convert the subset of Markdown this script emits into a styled, clickable HTML page."""
    def inline(s):
        s = html.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2" target="_blank">\1</a>', s)
        s = re.sub(r"(?<![\"=])(https?://[^\s<]+)", r'<a href="\1" target="_blank">\1</a>', s)
        return s
    out, in_ul = [], False
    for line in md.splitlines():
        if re.match(r"^\s*-\s", line):
            if not in_ul:
                out.append("<ul>"); in_ul = True
            indent = len(line) - len(line.lstrip())
            out.append(f'<li style="margin-left:{indent*8}px">{inline(line.lstrip()[2:])}</li>')
            continue
        if in_ul:
            out.append("</ul>"); in_ul = False
        if line.startswith("## "):
            out.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{inline(line[2:])}</h1>")
        elif line.startswith("> "):
            out.append(f"<blockquote>{inline(line[2:])}</blockquote>")
        elif line.strip() == "":
            out.append("")
        else:
            out.append(f"<p>{inline(line)}</p>")
    if in_ul:
        out.append("</ul>")
    body = "\n".join(out)
    return (f'<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            "<style>body{font-family:-apple-system,'PingFang SC',sans-serif;max-width:860px;margin:30px auto;"
            "padding:0 20px;line-height:1.6;color:#222}h1{border-bottom:2px solid #444;padding-bottom:8px}"
            "h2{margin-top:28px;background:#f4f7fa;padding:8px 12px;border-left:4px solid #2c7be5;border-radius:4px}"
            "blockquote{color:#666;background:#fafafa;border-left:3px solid #ccc;margin:8px 0;padding:6px 12px}"
            "ul{list-style:none;padding-left:0}li{padding:2px 0}a{color:#2c7be5;word-break:break-all}</style>"
            f"</head><body>{body}</body></html>")


def main():
    ap = argparse.ArgumentParser(description="温哥华华人分类网站租房搜索 (vanpeople + vansky)")
    ap.add_argument("--city", default="Burnaby", help="城市名，如 Burnaby / Richmond / Vancouver")
    ap.add_argument("--bedrooms", type=int, default=2, help="卧室数 (1-5)，默认 2")
    ap.add_argument("--max-price", type=int, default=1800, help="月租上限，默认 1800")
    ap.add_argument("--min-price", type=int, default=1, help="月租下限，默认 1")
    ap.add_argument("--rent-type", default="整租", choices=["整租", "分租", "any"], help="整租/分租/any，默认整租")
    ap.add_argument("--house-type", default="", help="房屋类型，逗号分隔：公寓,独立屋,连排屋,后巷屋")
    ap.add_argument("--rent-includes", default="", help="租金需包含，逗号分隔：水费,电费,网络,天然气")
    ap.add_argument("--facilities", default="", help="需具备设施：洗衣,独立厨房,基本电器,基本家具,中央空调,独立卫浴,独立车位,充电桩")
    ap.add_argument("--pets", default="", help="可养宠物：猫,狗")
    ap.add_argument("--posted-since", type=int, default=0, help="只看最近 N 天内发布/更新的房源（0=不限）")
    ap.add_argument("--available-from", default="", help="起租时间不早于 YYYY-MM-DD（需抓详情页）")
    ap.add_argument("--available-to", default="", help="起租时间不晚于 YYYY-MM-DD（需抓详情页）")
    ap.add_argument("--show-available", action="store_true", help="抓详情页补充每套的起租时间/最短租期")
    ap.add_argument("--above-ground", action="store_true", help="只要全地上（文字判断，非站点筛选项；排除半地下/地下室）")
    ap.add_argument("--source", default="vanpeople", choices=["vanpeople", "vansky", "both"])
    ap.add_argument("--pages", type=int, default=6, help="每个来源抓取的列表页数（按时间倒序），默认 6")
    ap.add_argument("--contacts", action="store_true", help="详细清单格式：每套含联系人/电话/邮箱/微信/链接")
    ap.add_argument("--out", help="输出 .md 文件路径（不填则打印到 stdout）")
    ap.add_argument("--json", action="store_true", help="输出结构化 JSON（便于其它程序/agent 解析）而非 Markdown")
    ap.add_argument("--html", action="store_true", help="同时生成排版好的 .html（链接可点）；配合 --out 写同名 .html，并在默认浏览器打开")
    ap.add_argument("--open", action="store_true", help="在 Chrome 中打开所有去重后的地上房源")
    args = ap.parse_args()

    try:
        rows = run_search(
            city=args.city, bedrooms=args.bedrooms, max_price=args.max_price, min_price=args.min_price,
            rent_type=args.rent_type, house_type=args.house_type, rent_includes=args.rent_includes,
            facilities=args.facilities, pets=args.pets, posted_since=args.posted_since,
            available_from=args.available_from, available_to=args.available_to,
            show_available=args.show_available, above_ground=args.above_ground,
            source=args.source, pages=args.pages)
    except ValueError as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        payload = json.dumps(rows, ensure_ascii=False, indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(payload + "\n")
            print(f"已写入 {args.out}（共 {len(rows)} 套，去重后）", file=sys.stderr)
        else:
            print(payload)
        return

    md = to_markdown_detailed(rows, args) if args.contacts else to_markdown(rows, args)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md + "\n")
        print(f"已写入 {args.out}（共 {len(rows)} 套，去重后）")
    elif not args.html:
        print(md)

    if args.html:
        base = args.out or f"{args.city}-{args.bedrooms}br-rentals.md"
        html_path = re.sub(r"\.md$", "", base) + ".html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(render_html(md, f"{args.city} {args.bedrooms}室租房"))
        print(f"已生成网页 {html_path}")
        open_in_browser(html_path)

    if args.open:
        urls = [r["links"][0] for r in rows if r["floor"] in ("above", "unknown")]
        for u in urls:
            open_in_browser(u)
        print(f"已在浏览器打开 {len(urls)} 个地上房源", file=sys.stderr)


if __name__ == "__main__":
    main()
