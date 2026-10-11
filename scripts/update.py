#!/usr/bin/env python3
"""每日更新解锁数据：抓取 Dropstab 公开解锁日历，生成 data/unlocks.json。

数据源：https://dropstab.com/vesting（公开页面，无需 key）
    + 各币种详情页 https://dropstab.com/coins/{slug}/vesting（含带日期的解锁事件）

用法：
    python3 scripts/update.py [--top 25] [--out data/unlocks.json]

MVP 阶段：人工维护 watchlist（WATCHLIST），脚本只更新这些币种的数据。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# MVP 范围说明：Dropstab 公开页只列出"有临近解锁"的约 50 个币种（多为中小市值），
# 主流大币种若无临近解锁则不在列表中——这正是免费数据源的覆盖边界，如实呈现。
# 付费 API（Tokenomist Pro / CryptoRank Pro）才能做到全覆盖。


def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="replace")


def parse_amount(s: str) -> float:
    """'93.65 M ARB' / '$1.31 B' / '6.79 B ARB' -> 数值（原单位换算到个）"""
    s = s.replace(",", "").strip()
    m = re.match(r"\$?([\d.]+)\s*([KMB])?\b", s)
    if not m:
        return 0.0
    val = float(m.group(1))
    mult = {"K": 1e3, "M": 1e6, "B": 1e9}.get(m.group(2) or "", 1)
    return val * mult


def parse_list_page(html: str) -> list[dict]:
    """解析 vesting 列表页表格，返回每币种的概览（含下次解锁数量/金额/占比）。"""
    rows = []
    # 每行以 coins/{slug}/vesting 链接开头
    for m in re.finditer(
        r'href="https://dropstab\.com/coins/([a-z0-9-]+)/vesting".*?'
        r'truncate uppercase">([A-Z0-9]+)</div>.*?'
        r'text-blue-600[^>]*>\$([\d.,]+)</span>.*?'
        r'text-xs text-gray-600[^>]*><span>\$([\d.,]+)\s*([KMB])</span><span> </span><span>\(<!-- -->([\d.]+)% of M\.Cap',
        html, re.S,
    ):
        slug, symbol, price, val, unit, pct = m.groups()
        rows.append({
            "slug": slug,
            "symbol": symbol,
            "price_usd": float(price.replace(",", "")),
            "next_unlock_usd": parse_amount(f"{val} {unit}"),
            "next_unlock_mcap_pct": float(pct),
        })
    # 补充：解锁数量（tokens）
    for m in re.finditer(
        r'href="https://dropstab\.com/coins/([a-z0-9-]+)/vesting".*?'
        r'<div>([\d.,]+)\s*([KMB])\s*[A-Z0-9]+\s*</div>\s*<div class="mt-1 text-xs',
        html, re.S,
    ):
        slug, amt, unit = m.groups()
        for r in rows:
            if r["slug"] == slug:
                r["next_unlock_tokens"] = parse_amount(f"{amt} {unit}")
    # 市值
    for m in re.finditer(
        r'href="https://dropstab\.com/coins/([a-z0-9-]+)/vesting".*?'
        r'tableCellSpacing">\$([\d.,]+)\s*([KMB])</span></div></div></td><td[^>]*role="cell"><div class="tableCellSpacing"><div><span>([\d.,]+)',
        html, re.S,
    ):
        slug, mcap, unit, _circ = m.groups()
        for r in rows:
            if r["slug"] == slug:
                r["market_cap_usd"] = parse_amount(f"{mcap} {unit}")
    return rows


def parse_detail_page(html: str) -> list[dict]:
    """解析币种详情页内嵌 JSON，返回带日期的解锁事件列表。"""
    m = re.search(r'<script[^>]*>(\{"props":.*?)</script>', html, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
        events = data["props"]["pageProps"].get("unlocks") or []
    except (json.JSONDecodeError, KeyError):
        return []
    out = []
    for e in events:
        try:
            out.append({
                "date": dt.datetime.fromtimestamp(e["date"] / 1000, tz=dt.timezone.utc).strftime("%Y-%m-%d"),
                "allocation": e.get("sale") or "unknown",
                "tokens": round(float(e.get("tokens") or 0), 2),
                "value_usd": round(float(e.get("usdAmount") or 0), 2),
                "mcap_pct": round(float(e.get("marketCapSharePercent") or 0), 3),
                "unlock_type": e.get("unlockType") or "unknown",
            })
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda x: x["date"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=25, help="按市值取前 N 个币种拉详情")
    ap.add_argument("--out", default="data/unlocks.json")
    ap.add_argument("--sleep", type=float, default=1.0, help="详情页抓取间隔秒数")
    args = ap.parse_args()

    print("fetching list page...", flush=True)
    coins = parse_list_page(fetch("https://dropstab.com/vesting"))
    print(f"parsed {len(coins)} coins from list", flush=True)
    coins.sort(key=lambda c: c.get("market_cap_usd", 0), reverse=True)

    # MVP：直接取列表页按市值排序的前 N 个（即有临近解锁的币种）
    wanted = coins[: args.top]
    print(f"fetching detail pages for {len(wanted)} coins...", flush=True)

    today = dt.date.today().isoformat()
    tokens = []
    for i, c in enumerate(wanted):
        try:
            time.sleep(args.sleep if i else 0)
            events = parse_detail_page(fetch(f"https://dropstab.com/coins/{c['slug']}/vesting"))
        except Exception as exc:  # noqa: BLE001
            print(f"  WARN {c['symbol']}: {exc}", flush=True)
            events = []
        future = [e for e in events if e["date"] >= today]
        tokens.append({
            "symbol": c["symbol"],
            "slug": c["slug"],
            "price_usd": c.get("price_usd"),
            "market_cap_usd": c.get("market_cap_usd"),
            "next_unlock_tokens": c.get("next_unlock_tokens"),
            "next_unlock_usd": c.get("next_unlock_usd"),
            "next_unlock_mcap_pct": c.get("next_unlock_mcap_pct"),
            "upcoming_events": future[:12],
            "events_count": len(future),
        })
        print(f"  {c['symbol']}: {len(future)} upcoming events", flush=True)

    payload = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "dropstab.com (public pages)",
        "disclaimer": "数据来自第三方公开页面整理，仅供参考，不构成投资建议；关键事件请以项目官方披露为准。",
        "tokens": tokens,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"wrote {args.out} ({len(tokens)} tokens)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
