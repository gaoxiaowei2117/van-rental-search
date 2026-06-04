#!/usr/bin/env python3
"""
Minimal stdio MCP server exposing the van-rental-search engine as a tool.

Zero third-party dependencies — implements just enough of the Model Context
Protocol (JSON-RPC 2.0 over newline-delimited stdio) to be usable by any
MCP-compatible agent (Claude Desktop/Code, Cursor, open-source agents, …).

Run:  python3 scripts/mcp_server.py
Register it with your agent as an stdio MCP server pointing at this file.

Exposes one tool:
  search_rentals(city, bedrooms, max_price, min_price, rent_type, house_type,
                 rent_includes, facilities, pets, posted_since, available_from,
                 available_to, above_ground, source, pages) -> JSON array of listings
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import search  # noqa: E402  (the engine; run_search lives here)

PROTOCOL_VERSION = "2024-11-05"

TOOL = {
    "name": "search_rentals",
    "description": (
        "Search Vancouver Chinese-classifieds (vanpeople + vansky) for rental listings. "
        "Filters by city, bedrooms, price, rent type, house type, included utilities, "
        "facilities, pets, freshness and move-in date; classifies above-ground vs basement; "
        "de-duplicates landlords by phone. Returns a JSON array of listings, each with "
        "price, floor, title, area, tel, tel2, name, email, wechat, available, lease, date, "
        "src, count and links."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "default": "Burnaby",
                     "description": "City name, e.g. Burnaby, Richmond, Vancouver, Coquitlam, Surrey, New West."},
            "bedrooms": {"type": "integer", "default": 2, "minimum": 1, "maximum": 5},
            "max_price": {"type": "integer", "default": 1800, "description": "Monthly rent ceiling."},
            "min_price": {"type": "integer", "default": 1},
            "rent_type": {"type": "string", "enum": ["整租", "分租", "any"], "default": "整租"},
            "house_type": {"type": "string", "default": "",
                           "description": "Comma list: 公寓,独立屋,连排屋,后巷屋"},
            "rent_includes": {"type": "string", "default": "",
                              "description": "Comma list: 水费,电费,网络,天然气"},
            "facilities": {"type": "string", "default": "",
                           "description": "Comma list: 洗衣,独立厨房,基本电器,基本家具,中央空调,独立卫浴,独立车位,充电桩"},
            "pets": {"type": "string", "default": "", "description": "Comma list: 猫,狗"},
            "posted_since": {"type": "integer", "default": 0,
                             "description": "Only listings posted/updated within N days (0 = no limit)."},
            "available_from": {"type": "string", "default": "", "description": "Move-in not earlier than YYYY-MM-DD."},
            "available_to": {"type": "string", "default": "", "description": "Move-in not later than YYYY-MM-DD."},
            "above_ground": {"type": "boolean", "default": False,
                             "description": "Keep only above-ground (drop 半地下/地下室)."},
            "source": {"type": "string", "enum": ["vanpeople", "vansky", "both"], "default": "vanpeople"},
            "pages": {"type": "integer", "default": 6,
                      "description": "List pages to crawl per source (more = more complete, slower)."},
        },
    },
}


def handle(method, params):
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "van-rental-search", "version": "1.0.0"},
        }
    if method == "tools/list":
        return {"tools": [TOOL]}
    if method == "tools/call":
        if params.get("name") != "search_rentals":
            raise ValueError(f"unknown tool: {params.get('name')}")
        args = params.get("arguments") or {}
        # only pass keys run_search understands
        allowed = {"city", "bedrooms", "max_price", "min_price", "rent_type", "house_type",
                   "rent_includes", "facilities", "pets", "posted_since", "available_from",
                   "available_to", "show_available", "above_ground", "source", "pages"}
        kwargs = {k: v for k, v in args.items() if k in allowed}
        rows = search.run_search(**kwargs)
        text = json.dumps(rows, ensure_ascii=False, indent=2)
        return {"content": [{"type": "text", "text": text}],
                "structuredContent": {"count": len(rows), "listings": rows}}
    raise ValueError(f"unknown method: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid = msg.get("id")
        method = msg.get("method", "")
        # notifications carry no id and expect no response
        if mid is None:
            continue
        try:
            result = handle(method, msg.get("params") or {})
            resp = {"jsonrpc": "2.0", "id": mid, "result": result}
        except Exception as e:  # surface errors per MCP tools/call convention
            if method == "tools/call":
                resp = {"jsonrpc": "2.0", "id": mid,
                        "result": {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True}}
            else:
                resp = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
