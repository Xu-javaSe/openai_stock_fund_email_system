"""
Stock + fund observation email system.

For learning and research only. This script creates observation reports, not
investment advice or buy/sell instructions.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import email.message
import html
import json
import math
import mimetypes
import os
import re
import socket
import smtplib
import ssl
import statistics
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "data" / "state.json"

EASTMONEY_LHB_API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
EASTMONEY_KLINE_API = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
TENCENT_KLINE_API = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
EASTMONEY_FUND_NAV_API = "https://api.fund.eastmoney.com/f10/lsjz"
THS_LHB_URL = "https://data.10jqka.com.cn/ifmarket/lhbggxq/"

CHANGE_MIN = 5.0
CHANGE_MAX = 10.0
SOURCE_WEIGHTS = {"tonghuashun": 0.70, "eastmoney": 0.30}
PLATFORM_LABELS = {"tonghuashun": "同花顺", "eastmoney": "东方财富"}

THEME_KEYWORDS = {
    "AI/算力/数据中心": [
        "AI",
        "人工智能",
        "算力",
        "数据中心",
        "云计算",
        "服务器",
        "光模块",
        "通信",
        "网宿",
        "浪潮",
        "中科曙光",
        "工业富联",
        "新易盛",
        "中际旭创",
        "寒武纪",
    ],
    "软件/网络安全": [
        "软件",
        "信创",
        "网络",
        "安全",
        "信息",
        "深信服",
        "绿盟",
        "启明星辰",
        "太极",
        "中国软件",
    ],
    "芯片/半导体材料": [
        "芯片",
        "半导体",
        "集成电路",
        "封测",
        "材料",
        "硅",
        "锗",
        "电子",
        "兆易",
        "北方华创",
        "中芯",
    ],
    "机器人/智能制造": ["机器人", "智能制造", "自动化", "减速器", "伺服", "机床"],
    "新能源/电力设备": ["新能源", "锂电", "光伏", "储能", "电池", "电力", "充电"],
    "医药/医疗": ["医药", "医疗", "创新药", "生物", "制药", "器械"],
}

THEME_SCORE = {
    "AI/算力/数据中心": 12,
    "软件/网络安全": 11,
    "芯片/半导体材料": 11,
    "机器人/智能制造": 9,
    "新能源/电力设备": 8,
    "医药/医疗": 8,
    "其他龙虎榜异动": 6,
}

FUND_THEME_MAP = {
    "AI/算力/数据中心": {
        "etf": [
            {"code": "159819", "name": "人工智能ETF"},
            {"code": "516510", "name": "云计算ETF"},
            {"code": "515880", "name": "通信ETF"},
        ],
        "otc": [
            {"code": "001409", "name": "工银互联网加股票"},
            {"code": "006751", "name": "富国互联科技股票A"},
            {"code": "008086", "name": "华夏中证5G通信主题ETF联接A"},
        ],
    },
    "软件/网络安全": {
        "etf": [
            {"code": "515230", "name": "软件ETF"},
            {"code": "159852", "name": "软件ETF"},
            {"code": "512720", "name": "计算机ETF"},
        ],
        "otc": [
            {"code": "012733", "name": "国泰中证全指软件ETF联接A"},
            {"code": "001409", "name": "工银互联网加股票"},
            {"code": "006751", "name": "富国互联科技股票A"},
        ],
    },
    "芯片/半导体材料": {
        "etf": [
            {"code": "159995", "name": "芯片ETF"},
            {"code": "512480", "name": "半导体ETF"},
            {"code": "588200", "name": "科创芯片ETF"},
        ],
        "otc": [
            {"code": "008281", "name": "国泰CES半导体芯片ETF联接A"},
            {"code": "013339", "name": "创金合信芯片产业股票A"},
            {"code": "014418", "name": "西部利得CES半导体芯片行业指数A"},
        ],
    },
    "机器人/智能制造": {
        "etf": [
            {"code": "562500", "name": "机器人ETF"},
            {"code": "159770", "name": "机器人ETF"},
            {"code": "512660", "name": "军工ETF"},
        ],
        "otc": [
            {"code": "001054", "name": "工银新金融股票A"},
            {"code": "001717", "name": "工银前沿医疗股票A"},
        ],
    },
    "新能源/电力设备": {
        "etf": [
            {"code": "515790", "name": "光伏ETF"},
            {"code": "516160", "name": "新能源ETF"},
            {"code": "159875", "name": "新能源ETF"},
        ],
        "otc": [
            {"code": "011329", "name": "景顺长城新能源产业股票A"},
            {"code": "005669", "name": "前海开源公用事业股票"},
        ],
    },
    "医药/医疗": {
        "etf": [
            {"code": "512170", "name": "医疗ETF"},
            {"code": "159929", "name": "医药ETF"},
            {"code": "512010", "name": "医药ETF"},
        ],
        "otc": [
            {"code": "003095", "name": "中欧医疗健康混合A"},
            {"code": "001717", "name": "工银前沿医疗股票A"},
        ],
    },
}


def now_cn() -> dt.datetime:
    return dt.datetime.utcnow() + dt.timedelta(hours=8)


def http_get_text(url: str, headers: dict[str, str] | None = None, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
        raw = response.read()
        content_type = response.headers.get("content-type", "")
    encoding = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    if match:
        encoding = match.group(1)
    return raw.decode(encoding, "replace")


def http_get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 20) -> dict[str, Any]:
    text = http_get_text(url, headers=headers, timeout=timeout)
    return json.loads(text)


def clean_html(text: str) -> str:
    text = re.sub(r"<script.*?</script>", "", text, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        text = str(value).replace(",", "").replace("%", "").strip()
        if not text or text in {"-", "--"}:
            return default
        number = float(text)
        return default if math.isnan(number) else number
    except (TypeError, ValueError):
        return default


def parse_money(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).replace(",", "").strip()
    if not text or text in {"-", "--"}:
        return 0.0
    sign = -1 if text.startswith("-") else 1
    text = text.lstrip("+-")
    match = re.search(r"([\d.]+)", text)
    if not match:
        return 0.0
    number = float(match.group(1))
    if "亿" in text:
        number *= 100000000
    elif "万" in text:
        number *= 10000
    return sign * number


def normalize_code(code: Any) -> str:
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else digits


def is_common_stock(code: str) -> bool:
    return bool(re.match(r"^(000|001|002|003|300|301|600|601|603|605|688)\d{3}$", code))


def market_id(code: str) -> str:
    return "1" if code.startswith(("5", "6", "9")) else "0"


def candidate_dates(trade_date: str, days: int = 8) -> list[str]:
    try:
        start = dt.date.fromisoformat(trade_date)
    except ValueError:
        start = now_cn().date()
    return [(start - dt.timedelta(days=i)).isoformat() for i in range(days)]


def detect_theme(code: str, name: str, reason: str = "") -> str:
    text = f"{code} {name} {reason}".upper()
    for theme, keywords in THEME_KEYWORDS.items():
        if any(keyword.upper() in text for keyword in keywords):
            return theme
    if code.startswith(("300", "301", "688")):
        return "其他龙虎榜异动"
    return "其他龙虎榜异动"


def fetch_eastmoney_lhb(trade_date: str) -> list[dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://data.eastmoney.com/stock/lhb.html",
    }
    raw_rows: list[dict[str, Any]] = []
    used_date = trade_date
    for date_text in candidate_dates(trade_date):
        params = {
            "sortColumns": "TRADE_DATE,SECURITY_CODE",
            "sortTypes": "-1,1",
            "pageSize": "500",
            "pageNumber": "1",
            "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
            "columns": "ALL",
            "source": "WEB",
            "client": "WEB",
            "filter": f"(TRADE_DATE='{date_text}')",
        }
        url = EASTMONEY_LHB_API + "?" + urllib.parse.urlencode(params)
        try:
            payload = http_get_json(url, headers=headers)
        except Exception:
            continue
        raw_rows = (payload.get("result") or {}).get("data") or []
        if raw_rows:
            used_date = date_text
            break

    rows = []
    for item in raw_rows:
        code = normalize_code(item.get("SECURITY_CODE"))
        if not is_common_stock(code):
            continue
        name = str(item.get("SECURITY_NAME_ABBR") or "")
        reason = str(item.get("EXPLANATION") or "")
        rows.append(
            {
                "source": "eastmoney",
                "source_date": used_date,
                "code": code,
                "name": name,
                "close": to_float(item.get("CLOSE_PRICE")),
                "change_rate": to_float(item.get("CHANGE_RATE")),
                "turnover_rate": to_float(item.get("TURNOVERRATE")),
                "buy_amount": to_float(item.get("BILLBOARD_BUY_AMT") or item.get("SUM_BUY_AMT")),
                "sell_amount": to_float(item.get("BILLBOARD_SELL_AMT") or item.get("SUM_SELL_AMT")),
                "net_buy": to_float(item.get("BILLBOARD_NET_AMT") or item.get("NET_BS_AMT")),
                "net_ratio": to_float(item.get("DEAL_NET_RATIO")),
                "deal_ratio": to_float(item.get("DEAL_AMOUNT_RATIO")),
                "reason": reason,
                "explain": str(item.get("EXPLAIN") or ""),
                "theme": detect_theme(code, name, reason),
            }
        )
    return rows


def fetch_tonghuashun_lhb(trade_date: str) -> list[dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://data.10jqka.com.cn/",
    }
    text = http_get_text(THS_LHB_URL, headers=headers)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.S | re.I):
        cells_html = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.S | re.I)
        if len(cells_html) < 5:
            continue
        cells = [clean_html(cell) for cell in cells_html]
        code_match = re.search(r"\b\d{6}\b", " ".join(cells))
        if not code_match:
            continue
        code = normalize_code(code_match.group(0))
        if code in seen or not is_common_stock(code):
            continue
        stock_link = re.search(r'stockcode=["\']?(\d{6})["\']?[^>]*>(.*?)</a>', row_html, flags=re.S | re.I)
        name = clean_html(stock_link.group(2)) if stock_link and stock_link.group(1) == code else ""
        if not name:
            code_index = next((i for i, cell in enumerate(cells) if code in cell), -1)
            if 0 <= code_index + 1 < len(cells):
                name = re.sub(r"\s+", "", cells[code_index + 1])
        pct_matches = []
        for cell in cells:
            pct_matches.extend(re.findall(r"[-+]?\d+(?:\.\d+)?%", cell))
        change_rate = to_float(pct_matches[0] if pct_matches else 0)
        if abs(change_rate) < 0.01:
            continue
        money_values = [parse_money(cell) for cell in cells if re.search(r"[万亿]", cell)]
        net_buy = money_values[-1] if money_values else 0.0
        close = 0.0
        for cell in cells:
            if "%" not in cell and re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cell):
                close = to_float(cell)
                break
        reason = "同花顺龙虎榜"
        rows.append(
            {
                "source": "tonghuashun",
                "source_date": trade_date,
                "code": code,
                "name": name,
                "close": close,
                "change_rate": change_rate,
                "turnover_rate": 0.0,
                "buy_amount": max(net_buy, 0.0),
                "sell_amount": max(-net_buy, 0.0),
                "net_buy": net_buy,
                "net_ratio": 0.0,
                "deal_ratio": 0.0,
                "reason": reason,
                "explain": "",
                "theme": detect_theme(code, name, reason),
            }
        )
        seen.add(code)
    return rows


def fetch_stock_history(code: str, days: int = 80, end_date: str | None = None) -> list[dict[str, Any]]:
    try:
        return fetch_eastmoney_history(code, days=days, end_date=end_date)
    except Exception:
        return fetch_tencent_history(code, days=days)


def fetch_eastmoney_history(code: str, days: int = 80, end_date: str | None = None) -> list[dict[str, Any]]:
    end = (end_date or "2050-01-01").replace("-", "")
    params = {
        "secid": f"{market_id(code)}.{code}",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "end": end,
        "lmt": str(days),
    }
    url = EASTMONEY_KLINE_API + "?" + urllib.parse.urlencode(params)
    payload = http_get_json(url, headers={"User-Agent": "Mozilla/5.0"})
    klines = ((payload.get("data") or {}).get("klines")) or []
    history = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 11:
            continue
        history.append(
            {
                "date": parts[0],
                "open": to_float(parts[1]),
                "close": to_float(parts[2]),
                "high": to_float(parts[3]),
                "low": to_float(parts[4]),
                "volume": to_float(parts[5]),
                "amount": to_float(parts[6]),
                "amplitude": to_float(parts[7]),
                "change_rate": to_float(parts[8]),
                "change_amount": to_float(parts[9]),
                "turnover_rate": to_float(parts[10]),
            }
        )
    return history


def fetch_tencent_history(code: str, days: int = 80) -> list[dict[str, Any]]:
    prefix = "sh" if market_id(code) == "1" else "sz"
    symbol = f"{prefix}{code}"
    params = {"param": f"{symbol},day,,,{days},qfq"}
    url = TENCENT_KLINE_API + "?" + urllib.parse.urlencode(params)
    payload = http_get_json(url, headers={"User-Agent": "Mozilla/5.0"})
    data = (payload.get("data") or {}).get(symbol) or {}
    rows = data.get("qfqday") or data.get("day") or []
    history = []
    previous_close = 0.0
    for item in rows:
        if len(item) < 6:
            continue
        close = to_float(item[2])
        change_rate = ((close - previous_close) / previous_close * 100) if previous_close else 0.0
        previous_close = close
        history.append(
            {
                "date": item[0],
                "open": to_float(item[1]),
                "close": close,
                "high": to_float(item[3]),
                "low": to_float(item[4]),
                "volume": to_float(item[5]),
                "amount": 0.0,
                "amplitude": 0.0,
                "change_rate": round(change_rate, 2),
                "change_amount": 0.0,
                "turnover_rate": 0.0,
            }
        )
    return history


def max_drawdown(values: list[float]) -> float:
    peak = 0.0
    worst = 0.0
    for value in values:
        if value <= 0:
            continue
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, (value - peak) / peak * 100)
    return round(abs(worst), 2)


def pct_change(values: list[float], days: int) -> float:
    if len(values) <= days or values[-days - 1] == 0:
        return 0.0
    return round((values[-1] - values[-days - 1]) / values[-days - 1] * 100, 2)


def analyze_price_history(history: list[dict[str, Any]]) -> dict[str, Any]:
    if len(history) < 20:
        return {
            "history_ok": False,
            "trend_status": "历史行情不足，趋势仅供参考",
            "pressure_status": "历史行情不足，压力位仅供参考",
            "consecutive_up": 0,
            "distance_20_high": 0.0,
            "distance_60_high": 0.0,
            "volume_ratio": 0.0,
            "max_drawdown_60": 0.0,
            "volatility_20": 0.0,
            "trend_score": 5,
            "pressure_score": 5,
            "risk_flags": ["历史行情不足"],
        }
    closes = [row["close"] for row in history if row["close"] > 0]
    highs = [row["high"] for row in history if row["high"] > 0]
    volumes = [row["volume"] for row in history if row["volume"] > 0]
    if len(closes) < 20 or len(highs) < 20:
        return analyze_price_history([])

    last_close = closes[-1]
    consecutive_up = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] > closes[i - 1]:
            consecutive_up += 1
        else:
            break

    ma5 = statistics.mean(closes[-5:])
    ma10 = statistics.mean(closes[-10:])
    ma20 = statistics.mean(closes[-20:])
    ma60 = statistics.mean(closes[-60:]) if len(closes) >= 60 else ma20
    high10 = max(highs[-10:])
    high20 = max(highs[-20:])
    high60 = max(highs[-60:]) if len(highs) >= 60 else high20
    distance_10 = round((high10 - last_close) / last_close * 100, 2) if last_close else 0.0
    distance_20 = round((high20 - last_close) / last_close * 100, 2) if last_close else 0.0
    distance_60 = round((high60 - last_close) / last_close * 100, 2) if last_close else 0.0
    avg_volume_20 = statistics.mean(volumes[-20:]) if len(volumes) >= 20 else 0.0
    volume_ratio = round(volumes[-1] / avg_volume_20, 2) if avg_volume_20 else 0.0
    daily_returns = [
        (closes[i] - closes[i - 1]) / closes[i - 1] * 100
        for i in range(1, len(closes))
        if closes[i - 1] > 0
    ]
    volatility_20 = round(statistics.pstdev(daily_returns[-20:]), 2) if len(daily_returns) >= 5 else 0.0
    drawdown_60 = max_drawdown(closes[-60:])

    if consecutive_up >= 3 and ma5 >= ma10 >= ma20:
        trend_status = f"连续上涨{consecutive_up}天，趋势延续"
        trend_score = 15
    elif ma5 >= ma10 and last_close >= ma20:
        trend_status = "短期均线向上，趋势偏强"
        trend_score = 12
    elif last_close >= ma20:
        trend_status = "站上20日均线，仍需确认"
        trend_score = 9
    else:
        trend_status = "低于20日均线，趋势偏弱"
        trend_score = 4

    if distance_20 <= 0.5:
        pressure_status = "贴近20日高点，容易遇到压力"
        pressure_score = 3
    elif distance_20 <= 2:
        pressure_status = f"距离20日高点{distance_20}%，接近压力位"
        pressure_score = 6
    else:
        pressure_status = f"距离20日高点{distance_20}%，尚未承压"
        pressure_score = 10

    flags = []
    if distance_20 <= 1.0:
        flags.append("接近20日压力")
    if last_close < ma20:
        flags.append("趋势偏弱")
    if volume_ratio >= 2.5:
        flags.append("放量过猛")
    if drawdown_60 >= 20:
        flags.append("近60日回撤偏大")

    return {
        "history_ok": True,
        "trend_status": trend_status,
        "pressure_status": pressure_status,
        "consecutive_up": consecutive_up,
        "ma5": round(ma5, 3),
        "ma10": round(ma10, 3),
        "ma20": round(ma20, 3),
        "ma60": round(ma60, 3),
        "distance_10_high": distance_10,
        "distance_20_high": distance_20,
        "distance_60_high": distance_60,
        "volume_ratio": volume_ratio,
        "max_drawdown_60": drawdown_60,
        "volatility_20": volatility_20,
        "return_5": pct_change(closes, 5),
        "return_20": pct_change(closes, 20),
        "return_60": pct_change(closes, 60) if len(closes) > 60 else 0.0,
        "trend_score": trend_score,
        "pressure_score": pressure_score,
        "risk_flags": flags,
    }


def risk_flags_for_source(row: dict[str, Any]) -> list[str]:
    flags = []
    name = row.get("name", "")
    reason = row.get("reason", "")
    if "退" in name or "退市" in reason:
        flags.append("退市风险")
    if "ST" in name.upper():
        flags.append("ST风险")
    if row.get("net_buy", 0) <= 0:
        flags.append("龙虎榜净卖出")
    turnover = row.get("turnover_rate", 0)
    if turnover >= 25:
        flags.append("换手过高")
    if 0 < turnover < 2:
        flags.append("流动性偏低")
    return flags


def score_source_row(row: dict[str, Any]) -> dict[str, Any]:
    change = row.get("change_rate", 0.0)
    net_buy_wan = row.get("net_buy", 0.0) / 10000
    net_ratio = max(row.get("net_ratio", 0.0), 0.0)
    turnover = row.get("turnover_rate", 0.0)
    explain = row.get("explain", "")

    if 6 <= change <= 8:
        change_score = 20
    elif 5 <= change < 6 or 8 < change <= 9.5:
        change_score = 16
    elif 9.5 < change <= 10:
        change_score = 12
    else:
        change_score = -40

    fund_score = min(max(net_buy_wan / 50000, 0), 1) * 18 + min(net_ratio / 18, 1) * 7
    seat_score = 8
    if "机构买入" in explain:
        seat_score += 4
    if any(token in explain for token in ["2家机构买入", "3家机构买入", "4家机构买入", "5家机构买入"]):
        seat_score += 3
    if "机构卖出" in explain:
        seat_score -= 4
    seat_score = max(0, min(seat_score, 15))

    liquidity_score = 7
    if 3 <= turnover <= 15:
        liquidity_score = 10
    elif turnover == 0:
        liquidity_score = 6
    elif 15 < turnover <= 25 or 2 <= turnover < 3:
        liquidity_score = 6
    else:
        liquidity_score = 2

    penalty = 0
    for flag in risk_flags_for_source(row):
        penalty += {"退市风险": 30, "ST风险": 20, "龙虎榜净卖出": 15, "换手过高": 6, "流动性偏低": 4}.get(flag, 3)

    score = fund_score + seat_score + THEME_SCORE.get(row["theme"], 6) + change_score + liquidity_score - penalty
    row = dict(row)
    row.update(
        {
            "source_score": round(max(0, min(score, 100)), 1),
            "source_risk_flags": risk_flags_for_source(row),
            "fund_score": round(fund_score, 1),
            "seat_score": round(seat_score, 1),
            "change_score": round(change_score, 1),
            "liquidity_score": round(liquidity_score, 1),
        }
    )
    return row


def collect_stock_records(trade_date: str) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    records: list[dict[str, Any]] = []
    source_counts = {"tonghuashun": 0, "eastmoney": 0}
    errors = []
    try:
        ths = fetch_tonghuashun_lhb(trade_date)
        source_counts["tonghuashun"] = len(ths)
        records.extend(ths)
    except Exception as exc:
        errors.append(f"同花顺抓取失败：{type(exc).__name__}: {exc}")
    try:
        em = fetch_eastmoney_lhb(trade_date)
        source_counts["eastmoney"] = len(em)
        records.extend(em)
    except Exception as exc:
        errors.append(f"东方财富抓取失败：{type(exc).__name__}: {exc}")
    return records, source_counts, errors


def merge_stock_records(records: list[dict[str, Any]], trade_date: str, previous_state: dict[str, Any]) -> list[dict[str, Any]]:
    best_by_source: dict[tuple[str, str], dict[str, Any]] = {}
    for row in records:
        scored = score_source_row(row)
        key = (scored["code"], scored["source"])
        old = best_by_source.get(key)
        if old is None or scored["source_score"] > old["source_score"]:
            best_by_source[key] = scored

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in best_by_source.values():
        grouped.setdefault(row["code"], []).append(row)

    merged: list[dict[str, Any]] = []
    for code, source_rows in grouped.items():
        source_rows.sort(key=lambda item: item["source_score"], reverse=True)
        primary = source_rows[0]
        active_weight = sum(SOURCE_WEIGHTS.get(row["source"], 0) for row in source_rows)
        if active_weight <= 0:
            continue
        source_score = sum(row["source_score"] * SOURCE_WEIGHTS.get(row["source"], 0) for row in source_rows) / active_weight
        change_rate = next((row["change_rate"] for row in source_rows if row.get("change_rate")), primary["change_rate"])
        if not (CHANGE_MIN <= change_rate <= CHANGE_MAX):
            continue

        all_flags: list[str] = []
        for row in source_rows:
            for flag in row.get("source_risk_flags", []):
                if flag not in all_flags:
                    all_flags.append(flag)
        reasons = [row.get("reason", "") for row in source_rows if row.get("reason")]
        explains = [row.get("explain", "") for row in source_rows if row.get("explain")]
        source_scores = {
            row["source"]: {
                "score": row["source_score"],
                "weight": round(SOURCE_WEIGHTS.get(row["source"], 0) * 100, 1),
                "net_buy": row.get("net_buy", 0),
            }
            for row in source_rows
        }

        history: list[dict[str, Any]] = []
        history_note = ""
        try:
            history = fetch_stock_history(code, days=80, end_date=trade_date)
        except Exception as exc:
            history_note = f"历史行情抓取失败：{type(exc).__name__}"
        history_info = analyze_price_history(history)

        risk_flags = list(all_flags)
        for flag in history_info.get("risk_flags", []):
            if flag not in risk_flags:
                risk_flags.append(flag)
        risk_points = sum(
            {
                "退市风险": 30,
                "ST风险": 20,
                "龙虎榜净卖出": 8,
                "换手过高": 5,
                "流动性偏低": 4,
                "接近20日压力": 4,
                "趋势偏弱": 5,
                "放量过猛": 3,
                "近60日回撤偏大": 3,
                "历史行情不足": 2,
            }.get(flag, 2)
            for flag in risk_flags
        )
        if risk_points >= 10:
            risk_level = "高风险"
        elif risk_points >= 4:
            risk_level = "中风险"
        else:
            risk_level = "低风险"

        final_score = 35 + source_score * 0.55 + history_info["trend_score"] * 1.3 + history_info["pressure_score"] * 0.9
        final_score -= min(risk_points * 1.8, 28)
        if risk_level == "高风险":
            final_score = min(final_score, 55)
        elif risk_level == "中风险":
            final_score = min(final_score, 75)
        final_score = round(max(0, min(final_score, 100)), 1)

        if risk_level == "高风险":
            group = "风险回避池"
            action_tip = "风险偏高，仅观察不参与"
        elif history_info.get("distance_20_high", 99) <= 2:
            group = "突破确认池"
            action_tip = "接近压力位，等待放量突破，不追高"
        elif history_info.get("trend_score", 0) >= 12 and risk_level == "低风险":
            group = "低吸观察池"
            action_tip = "趋势偏强，可观察回踩承接，不追高"
        else:
            group = "只看不追池"
            action_tip = "强度适中但条件未完全确认，先观察"

        prev = previous_state.get("stocks", {}).get(code, {})
        prev_streak = int(prev.get("streak", 0) or 0)
        memory_streak = prev_streak + 1
        memory_note = f"连续{memory_streak}次进入观察池" if prev_streak else "首次进入观察池"

        row = {
            "code": code,
            "name": primary["name"],
            "date": trade_date,
            "close": primary.get("close", 0) or (history[-1]["close"] if history else 0),
            "change_rate": round(change_rate, 2),
            "turnover_rate": max(row.get("turnover_rate", 0) for row in source_rows),
            "theme": primary["theme"],
            "score": final_score,
            "recommend_ratio": final_score,
            "source_score": round(source_score, 1),
            "platform_confidence": round(active_weight * 100, 1),
            "platforms": "；".join(PLATFORM_LABELS.get(row["source"], row["source"]) for row in source_rows),
            "source_scores": source_scores,
            "net_buy": max(row.get("net_buy", 0) for row in source_rows),
            "net_ratio": max(row.get("net_ratio", 0) for row in source_rows),
            "reason": "；".join(dict.fromkeys(reasons)),
            "explain": "；".join(dict.fromkeys(explains)),
            "risk_flags": risk_flags,
            "risk_level": risk_level,
            "risk_points": risk_points,
            "group": group,
            "action_tip": action_tip,
            "history_note": history_note,
            "memory_note": memory_note,
        }
        row.update(history_info)
        merged.append(row)

    attach_theme_linkage(merged)
    for row in merged:
        if row["theme_linkage"] == "联动强":
            row["score"] = min(100, round(row["score"] + 4, 1))
        elif row["theme_linkage"] == "联动中":
            row["score"] = min(100, round(row["score"] + 2, 1))
        if row["risk_level"] == "高风险":
            row["score"] = min(row["score"], 58)
        elif row["risk_level"] == "中风险":
            row["score"] = min(row["score"], 76)
        row["recommend_ratio"] = row["score"]
    return sorted(merged, key=lambda item: (item["score"], item["net_buy"]), reverse=True)


def attach_theme_linkage(rows: list[dict[str, Any]]) -> None:
    summary: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = summary.setdefault(row["theme"], {"count": 0, "high_count": 0, "score_sum": 0.0})
        item["count"] += 1
        item["score_sum"] += row["score"]
        if row["score"] >= 60:
            item["high_count"] += 1
    for row in rows:
        item = summary[row["theme"]]
        avg = item["score_sum"] / max(item["count"], 1)
        if item["high_count"] >= 3 and avg >= 60:
            linkage = "联动强"
        elif item["high_count"] >= 2:
            linkage = "联动中"
        elif item["count"] >= 2:
            linkage = "联动弱"
        else:
            linkage = "孤立异动"
        row["theme_peer_count"] = item["count"]
        row["theme_high_count"] = item["high_count"]
        row["theme_avg_score"] = round(avg, 1)
        row["theme_linkage"] = linkage


def summary_by_theme(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = summary.setdefault(row["theme"], {"theme": row["theme"], "count": 0, "score_sum": 0.0, "high_count": 0})
        item["count"] += 1
        item["score_sum"] += row["score"]
        if row["score"] >= 60:
            item["high_count"] += 1
    result = []
    for item in summary.values():
        avg = item["score_sum"] / item["count"]
        if item["high_count"] >= 3 and avg >= 60:
            linkage = "联动强"
        elif item["high_count"] >= 2:
            linkage = "联动中"
        elif item["count"] >= 2:
            linkage = "联动弱"
        else:
            linkage = "孤立异动"
        result.append(
            {
                "theme": item["theme"],
                "count": item["count"],
                "high_count": item["high_count"],
                "avg_score": round(avg, 1),
                "linkage": linkage,
            }
        )
    return sorted(result, key=lambda item: (item["high_count"], item["avg_score"], item["count"]), reverse=True)


def group_rows(rows: list[dict[str, Any]], group_key: str = "group") -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(row[group_key], []).append(row)
    for key in result:
        result[key].sort(key=lambda item: item["score"], reverse=True)
    return result


def fetch_otc_fund_nav(code: str, days: int = 90) -> list[dict[str, Any]]:
    params = {
        "fundCode": code,
        "pageIndex": "1",
        "pageSize": str(days),
        "startDate": "",
        "endDate": "",
    }
    url = EASTMONEY_FUND_NAV_API + "?" + urllib.parse.urlencode(params)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": f"https://fundf10.eastmoney.com/jjjz_{code}.html",
    }
    payload = http_get_json(url, headers=headers)
    rows = ((payload.get("Data") or {}).get("LSJZList")) or []
    history = []
    for item in reversed(rows):
        history.append(
            {
                "date": item.get("FSRQ", ""),
                "close": to_float(item.get("DWJZ")),
                "change_rate": to_float(item.get("JZZZL")),
                "volume": 0.0,
                "high": to_float(item.get("DWJZ")),
                "low": to_float(item.get("DWJZ")),
            }
        )
    return history


def fund_candidates(theme_summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    themes = [item["theme"] for item in theme_summary if item["count"] > 0][:4]
    if not themes:
        themes = ["AI/算力/数据中心", "芯片/半导体材料", "软件/网络安全"]
    seen: set[tuple[str, str]] = set()
    candidates = []
    for theme in themes:
        mapping = FUND_THEME_MAP.get(theme)
        if not mapping:
            continue
        for kind in ("etf", "otc"):
            for item in mapping.get(kind, []):
                key = (kind, item["code"])
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({"type": kind, "theme": theme, **item})
    return candidates


def analyze_funds(theme_summary: list[dict[str, Any]], previous_state: dict[str, Any], trade_date: str) -> list[dict[str, Any]]:
    funds = []
    for candidate in fund_candidates(theme_summary):
        code = candidate["code"]
        try:
            if candidate["type"] == "etf":
                history = fetch_stock_history(code, days=90, end_date=trade_date)
            else:
                history = fetch_otc_fund_nav(code, days=90)
        except Exception:
            continue
        info = analyze_price_history(history)
        if not history or not info.get("history_ok"):
            continue
        risk_flags = list(info.get("risk_flags", []))
        drawdown = info.get("max_drawdown_60", 0)
        volatility = info.get("volatility_20", 0)
        if drawdown >= 12:
            risk_flags.append("回撤偏大")
        if volatility >= 3:
            risk_flags.append("波动偏高")
        if info.get("distance_20_high", 99) <= 1.5:
            risk_flags.append("接近阶段高点")

        trend_points = info["trend_score"] * 2.0
        pressure_points = info["pressure_score"] * 1.4
        drawdown_points = max(0, 20 - min(drawdown, 20))
        volatility_points = max(0, 12 - min(volatility * 2, 12))
        score = round(min(100, 20 + trend_points + pressure_points + drawdown_points + volatility_points), 1)

        if "接近阶段高点" in risk_flags:
            group = "高位谨慎池"
            action_tip = "接近阶段高点，等待回落后再观察"
        elif score >= 72 and info.get("trend_score", 0) >= 12:
            group = "趋势观察池"
            action_tip = "趋势偏强，可继续跟踪板块延续性"
        elif drawdown <= 10 and info.get("return_20", 0) > 0:
            group = "回调低吸池"
            action_tip = "趋势未坏，适合等回调企稳信号"
        else:
            group = "暂不参与池"
            action_tip = "趋势或风险条件不够好，暂不参与"

        prev = previous_state.get("funds", {}).get(f"{candidate['type']}:{code}", {})
        prev_streak = int(prev.get("streak", 0) or 0)
        memory_streak = prev_streak + 1
        memory_note = f"连续{memory_streak}次进入基金观察池" if prev_streak else "首次进入基金观察池"

        fund = {
            "type": "ETF" if candidate["type"] == "etf" else "场外基金",
            "code": code,
            "name": candidate["name"],
            "theme": candidate["theme"],
            "score": score,
            "group": group,
            "action_tip": action_tip,
            "risk_flags": risk_flags,
            "risk_level": "高风险" if len(risk_flags) >= 3 else ("中风险" if risk_flags else "低风险"),
            "memory_note": memory_note,
        }
        fund.update(info)
        funds.append(fund)
        time.sleep(0.08)
    return sorted(funds, key=lambda item: item["score"], reverse=True)


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"last_run": "", "themes": {}, "stocks": {}, "funds": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"last_run": "", "themes": {}, "stocks": {}, "funds": {}}


def save_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def update_state(
    previous_state: dict[str, Any],
    stocks: list[dict[str, Any]],
    funds: list[dict[str, Any]],
    themes: list[dict[str, Any]],
    trade_date: str,
    mode: str,
) -> dict[str, Any]:
    new_state = {
        "last_run": now_cn().strftime("%Y-%m-%d %H:%M:%S"),
        "last_trade_date": trade_date,
        "last_mode": mode,
        "themes": {},
        "stocks": {},
        "funds": {},
    }
    previous_themes = previous_state.get("themes", {})
    for item in themes:
        prev = previous_themes.get(item["theme"], {})
        streak = int(prev.get("streak", 0) or 0) + 1
        new_state["themes"][item["theme"]] = {
            "streak": streak,
            "last_linkage": item["linkage"],
            "last_avg_score": item["avg_score"],
            "last_count": item["count"],
        }
    previous_stocks = previous_state.get("stocks", {})
    for row in stocks:
        prev = previous_stocks.get(row["code"], {})
        streak = int(prev.get("streak", 0) or 0) + 1
        new_state["stocks"][row["code"]] = {
            "name": row["name"],
            "streak": streak,
            "last_group": row["group"],
            "last_score": row["score"],
            "last_theme": row["theme"],
        }
    previous_funds = previous_state.get("funds", {})
    for fund in funds:
        key = f"{fund['type']}:{fund['code']}"
        prev = previous_funds.get(key, {})
        streak = int(prev.get("streak", 0) or 0) + 1
        new_state["funds"][key] = {
            "name": fund["name"],
            "streak": streak,
            "last_group": fund["group"],
            "last_score": fund["score"],
            "last_theme": fund["theme"],
        }
    return new_state


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def pct(value: Any, digits: int = 1) -> str:
    return f"{to_float(value):.{digits}f}%"


def wan(value: Any) -> str:
    return f"{to_float(value) / 10000:.1f}万"


def risk_class(risk_level: str) -> str:
    return {"低风险": "ok", "中风险": "warn", "高风险": "danger"}.get(risk_level, "warn")


def render_group_cards(groups: dict[str, list[dict[str, Any]]], group_order: list[str], kind: str = "stock") -> str:
    cards = []
    for group in group_order:
        rows = groups.get(group, [])
        if not rows:
            continue
        items = []
        for row in rows[:8]:
            if kind == "stock":
                subtitle = f"{row['code']} | {pct(row['change_rate'])} | {row['theme']} | {row['risk_level']}"
            else:
                subtitle = f"{row['code']} | {row['type']} | {row['theme']} | {row['risk_level']}"
            items.append(
                f"""
                <div class="mini-item">
                  <div><b>{esc(row['name'])}</b> <span class="score">{esc(row['score'])}</span></div>
                  <div class="muted">{esc(subtitle)}</div>
                  <div class="muted">{esc(row.get('action_tip', ''))}</div>
                </div>
                """
            )
        cards.append(
            f"""
            <div class="pool">
              <div class="pool-title">{esc(group)} <span>{len(rows)}只</span></div>
              {''.join(items)}
            </div>
            """
        )
    return "".join(cards) or '<p class="muted">暂无符合条件的观察对象。</p>'


def render_stock_table(rows: list[dict[str, Any]]) -> str:
    body = []
    for idx, row in enumerate(rows[:20], 1):
        risks = "；".join(row["risk_flags"]) if row["risk_flags"] else "无明显风险"
        body.append(
            f"""
            <tr>
              <td>{idx}</td>
              <td><b>{esc(row['name'])}</b><br><span class="muted">{esc(row['code'])}</span></td>
              <td><b>{pct(row['recommend_ratio'])}</b><br><span class="muted">涨幅 {pct(row['change_rate'])}</span></td>
              <td>{esc(row['theme'])}<br><span class="pill">{esc(row['theme_linkage'])}，同向{row['theme_peer_count']}只</span></td>
              <td>{esc(row['trend_status'])}<br><span class="muted">量比 {esc(row.get('volume_ratio', 0))}</span></td>
              <td>{esc(row['pressure_status'])}</td>
              <td><span class="tag {risk_class(row['risk_level'])}">{esc(row['risk_level'])}</span><br><span class="muted">{esc(risks)}</span></td>
              <td>{esc(row['action_tip'])}<br><span class="muted">{esc(row['memory_note'])}</span></td>
            </tr>
            """
        )
    return "".join(body)


def render_fund_table(funds: list[dict[str, Any]]) -> str:
    body = []
    for idx, fund in enumerate(funds[:20], 1):
        risks = "；".join(fund["risk_flags"]) if fund["risk_flags"] else "无明显风险"
        body.append(
            f"""
            <tr>
              <td>{idx}</td>
              <td><b>{esc(fund['name'])}</b><br><span class="muted">{esc(fund['code'])} | {esc(fund['type'])}</span></td>
              <td><b>{esc(fund['score'])}</b><br><span class="muted">{esc(fund['group'])}</span></td>
              <td>{esc(fund['theme'])}</td>
              <td>{esc(fund['trend_status'])}<br><span class="muted">20日 {pct(fund.get('return_20', 0))}</span></td>
              <td>{esc(fund['pressure_status'])}<br><span class="muted">回撤 {pct(fund.get('max_drawdown_60', 0))}</span></td>
              <td><span class="tag {risk_class(fund['risk_level'])}">{esc(fund['risk_level'])}</span><br><span class="muted">{esc(risks)}</span></td>
              <td>{esc(fund['action_tip'])}<br><span class="muted">{esc(fund['memory_note'])}</span></td>
            </tr>
            """
        )
    return "".join(body)


def render_html_report(report: dict[str, Any]) -> str:
    stocks = report["stocks"]
    funds = report["funds"]
    stock_groups = group_rows(stocks)
    fund_groups = group_rows(funds)
    themes = report["themes"]
    mode_label = "14点综合观察" if report["mode"] == "full" else "12点股票观察"
    best_line = (
        f"今日符合5%-10%涨幅硬条件的股票共 {len(stocks)} 只，最高观察对象为 {stocks[0]['name']}（{stocks[0]['recommend_ratio']}%）。"
        if stocks
        else "今日暂未筛出符合5%-10%涨幅硬条件的龙虎榜股票。"
    )
    theme_html = "".join(
        f"""
        <div class="theme-row">
          <b>{esc(item['theme'])}</b>
          <span>{esc(item['linkage'])} | {item['count']}只 | 高分{item['high_count']}只 | 均分{item['avg_score']}</span>
        </div>
        """
        for item in themes[:8]
    )
    if not theme_html:
        theme_html = '<p class="muted">暂无强方向。</p>'

    fund_section = ""
    if report["mode"] == "full":
        fund_section = f"""
        <section class="card">
          <h2>基金/ETF观察池</h2>
          <div class="pools">
            {render_group_cards(fund_groups, ["趋势观察池", "回调低吸池", "高位谨慎池", "暂不参与池"], kind="fund")}
          </div>
        </section>
        <section class="card">
          <h2>基金/ETF详情</h2>
          <table>
            <thead><tr><th>#</th><th>基金</th><th>评分/分组</th><th>匹配方向</th><th>趋势</th><th>压力/回撤</th><th>风险</th><th>观察提示</th></tr></thead>
            <tbody>{render_fund_table(funds)}</tbody>
          </table>
        </section>
        """

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(mode_label)} - {esc(report['trade_date'])}</title>
  <style>
    body {{ margin:0; background:#f6f8fb; color:#172033; font-family:Arial,'Microsoft YaHei',sans-serif; line-height:1.55; }}
    .wrap {{ max-width:1180px; margin:0 auto; padding:18px; }}
    .hero {{ background:#10233f; color:white; border-radius:8px; padding:20px; }}
    h1 {{ margin:0 0 8px; font-size:24px; }}
    h2 {{ margin:0 0 12px; font-size:18px; }}
    .muted {{ color:#667085; font-size:12px; }}
    .hero .muted {{ color:#d8e4f5; }}
    .grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:14px 0; }}
    .metric,.card,.pool {{ background:white; border:1px solid #e4e7ec; border-radius:8px; padding:14px; }}
    .metric b {{ display:block; font-size:24px; margin-top:4px; }}
    .card {{ margin-top:14px; }}
    .pools {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
    .pool-title {{ font-weight:700; margin-bottom:8px; display:flex; justify-content:space-between; }}
    .mini-item {{ border-top:1px solid #eef1f5; padding:8px 0; }}
    .score {{ color:#2563eb; font-weight:700; }}
    .theme-row {{ display:flex; justify-content:space-between; gap:12px; padding:8px 0; border-bottom:1px solid #eef1f5; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ padding:9px 7px; border-bottom:1px solid #e4e7ec; vertical-align:top; text-align:left; }}
    th {{ background:#f9fafb; }}
    .pill {{ display:inline-block; margin-top:3px; padding:2px 7px; border-radius:999px; background:#eef2ff; color:#3730a3; font-size:12px; }}
    .tag {{ display:inline-block; padding:2px 7px; border-radius:999px; font-size:12px; font-weight:700; }}
    .ok {{ background:#ecfdf3; color:#027a48; }}
    .warn {{ background:#fff7e6; color:#b54708; }}
    .danger {{ background:#fef3f2; color:#b42318; }}
    .notice {{ font-size:12px; color:#667085; margin-top:12px; }}
    @media(max-width:900px) {{ .grid,.pools {{ grid-template-columns:1fr; }} .wrap {{ padding:10px; }} table {{ font-size:12px; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>{esc(mode_label)} - {esc(report['trade_date'])}</h1>
      <div>{esc(best_line)}</div>
      <div class="muted">硬规则：只筛选当日涨幅 5%-10% 的龙虎榜股票；同花顺70% + 东方财富30%；本报告仅用于观察和研究。</div>
    </section>
    <section class="grid">
      <div class="metric">股票候选<b>{len(stocks)}</b></div>
      <div class="metric">强方向<b>{sum(1 for item in themes if item['linkage'] in ('联动强','联动中'))}</b></div>
      <div class="metric">低吸观察<b>{len(stock_groups.get('低吸观察池', []))}</b></div>
      <div class="metric">基金候选<b>{len(funds) if report['mode'] == 'full' else '-'}</b></div>
    </section>
    <section class="card">
      <h2>强方向 / 板块联动</h2>
      {theme_html}
    </section>
    <section class="card">
      <h2>股票观察池</h2>
      <div class="pools">
        {render_group_cards(stock_groups, ["低吸观察池", "突破确认池", "只看不追池", "风险回避池"], kind="stock")}
      </div>
    </section>
    {fund_section}
    <section class="card">
      <h2>股票详情</h2>
      <table>
        <thead><tr><th>#</th><th>股票</th><th>推荐比例</th><th>方向/联动</th><th>趋势</th><th>压力位</th><th>风险</th><th>操作提示</th></tr></thead>
        <tbody>{render_stock_table(stocks)}</tbody>
      </table>
    </section>
    <div class="notice">
      数据源记录：同花顺 {report['source_counts'].get('tonghuashun', 0)} 条，东方财富 {report['source_counts'].get('eastmoney', 0)} 条。
      {esc('；'.join(report.get('errors', [])))}
      本系统不构成任何股票、基金、证券或金融产品的买卖建议。
    </div>
  </div>
</body>
</html>"""


def write_stock_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "rank",
        "group",
        "code",
        "name",
        "score",
        "recommend_ratio",
        "change_rate",
        "theme",
        "theme_linkage",
        "risk_level",
        "trend_status",
        "pressure_status",
        "action_tip",
        "memory_note",
        "platforms",
        "net_buy_wan",
        "turnover_rate",
        "risk_flags",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for rank, row in enumerate(rows, 1):
            writer.writerow(
                {
                    "rank": rank,
                    "group": row["group"],
                    "code": row["code"],
                    "name": row["name"],
                    "score": row["score"],
                    "recommend_ratio": f"{row['recommend_ratio']}%",
                    "change_rate": f"{row['change_rate']}%",
                    "theme": row["theme"],
                    "theme_linkage": row["theme_linkage"],
                    "risk_level": row["risk_level"],
                    "trend_status": row["trend_status"],
                    "pressure_status": row["pressure_status"],
                    "action_tip": row["action_tip"],
                    "memory_note": row["memory_note"],
                    "platforms": row["platforms"],
                    "net_buy_wan": round(row["net_buy"] / 10000, 2),
                    "turnover_rate": row["turnover_rate"],
                    "risk_flags": "；".join(row["risk_flags"]) or "无",
                }
            )


def write_fund_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "rank",
        "type",
        "group",
        "code",
        "name",
        "theme",
        "score",
        "risk_level",
        "trend_status",
        "pressure_status",
        "return_5",
        "return_20",
        "max_drawdown_60",
        "volatility_20",
        "action_tip",
        "memory_note",
        "risk_flags",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for rank, row in enumerate(rows, 1):
            writer.writerow(
                {
                    "rank": rank,
                    "type": row["type"],
                    "group": row["group"],
                    "code": row["code"],
                    "name": row["name"],
                    "theme": row["theme"],
                    "score": row["score"],
                    "risk_level": row["risk_level"],
                    "trend_status": row["trend_status"],
                    "pressure_status": row["pressure_status"],
                    "return_5": row.get("return_5", 0),
                    "return_20": row.get("return_20", 0),
                    "max_drawdown_60": row.get("max_drawdown_60", 0),
                    "volatility_20": row.get("volatility_20", 0),
                    "action_tip": row["action_tip"],
                    "memory_note": row["memory_note"],
                    "risk_flags": "；".join(row["risk_flags"]) or "无",
                }
            )


def attach_file(message: email.message.EmailMessage, path: Path) -> None:
    ctype, encoding = mimetypes.guess_type(str(path))
    if ctype is None or encoding is not None:
        ctype = "application/octet-stream"
    maintype, subtype = ctype.split("/", 1)
    message.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)


def clean_secret_value(value: str, secret_name: str) -> str:
    text = str(value or "").strip().strip('"').strip("'")
    prefix = f"{secret_name}="
    if text.upper().startswith(prefix):
        text = text[len(prefix) :].strip()
    return text


def clean_smtp_host(value: str) -> str:
    host = clean_secret_value(value, "SMTP_HOST")
    host = re.sub(r"^https?://", "", host, flags=re.I)
    host = host.split("/")[0].strip()
    host = host.rstrip("，,。；;")
    if host.count(":") == 1:
        host_part, port_part = host.rsplit(":", 1)
        if port_part.strip().isdigit():
            host = host_part.strip()
    return host


def resolve_smtp_host(host: str, port: int) -> None:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
            return
        except socket.gaierror as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(
        "SMTP_HOST 无法解析。请确认 GitHub Secret 里的 SMTP_HOST 只填类似 "
        "'smtp.qq.com'，不要带 'SMTP_HOST='、'https://'、端口号、空格或中文标点。"
    ) from last_error


def send_email(subject: str, html_body: str, attachments: list[Path]) -> None:
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "MAIL_TO"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    smtp_host = clean_smtp_host(os.environ["SMTP_HOST"])
    smtp_port = int(clean_secret_value(os.environ["SMTP_PORT"], "SMTP_PORT"))
    smtp_user = clean_secret_value(os.environ["SMTP_USER"], "SMTP_USER")
    smtp_password = clean_secret_value(os.environ["SMTP_PASSWORD"], "SMTP_PASSWORD")
    mail_to = clean_secret_value(os.environ["MAIL_TO"], "MAIL_TO")
    mail_from = clean_secret_value(os.environ.get("MAIL_FROM", smtp_user), "MAIL_FROM")

    resolve_smtp_host(smtp_host, smtp_port)

    message = email.message.EmailMessage()
    message["Subject"] = subject
    message["From"] = mail_from
    message["To"] = mail_to
    message.set_content("请使用支持 HTML 的邮件客户端查看观察报告。")
    message.add_alternative(html_body, subtype="html")
    for path in attachments:
        if path.exists():
            attach_file(message, path)

    context = ssl.create_default_context()
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
            server.login(smtp_user, smtp_password)
            server.send_message(message)
    else:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_password)
            server.send_message(message)


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    previous_state = load_state()
    records, source_counts, errors = collect_stock_records(args.date)
    stocks = merge_stock_records(records, args.date, previous_state)[: args.top]
    themes = summary_by_theme(stocks)
    funds: list[dict[str, Any]] = []
    if args.mode == "full":
        funds = analyze_funds(themes, previous_state, args.date)[: args.fund_top]
    report = {
        "trade_date": args.date,
        "generated_at": now_cn().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": args.mode,
        "source_counts": source_counts,
        "errors": errors,
        "stocks": stocks,
        "themes": themes,
        "funds": funds,
    }
    new_state = update_state(previous_state, stocks, funds, themes, args.date, args.mode)
    save_state(new_state)
    return report


def write_outputs(report: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    html_text = render_html_report(report)
    paths = {
        "email": output_dir / "email_preview.html",
        "dashboard": output_dir / "dashboard.html",
        "stock_csv": output_dir / "stock_scores.csv",
        "fund_csv": output_dir / "fund_scores.csv",
        "json": output_dir / "report.json",
    }
    paths["email"].write_text(html_text, encoding="utf-8")
    paths["dashboard"].write_text(html_text, encoding="utf-8")
    write_stock_csv(report["stocks"], paths["stock_csv"])
    write_fund_csv(report["funds"], paths["fund_csv"])
    paths["json"].write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stock + fund observation email system.")
    parser.add_argument("--date", default=now_cn().date().isoformat(), help="Trade date, e.g. 2026-07-08")
    parser.add_argument("--mode", choices=["stock", "full"], default=os.environ.get("REPORT_MODE", "stock"))
    parser.add_argument("--output", default="output", help="Output directory")
    parser.add_argument("--top", type=int, default=30, help="Max stock rows")
    parser.add_argument("--fund-top", type=int, default=24, help="Max fund rows")
    parser.add_argument("--dry-run", action="store_true", help="Generate files without sending email")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output)
    report = build_report(args)
    paths = write_outputs(report, output_dir)
    mode_label = "14点综合观察" if args.mode == "full" else "12点股票观察"
    subject_prefix = os.environ.get("MAIL_SUBJECT_PREFIX", "股票基金观察邮件")
    subject = f"{subject_prefix} - {mode_label} - {args.date}"
    attachments = [paths["stock_csv"], paths["dashboard"]]
    if args.mode == "full":
        attachments.append(paths["fund_csv"])
    if args.dry_run:
        print("Dry run: email not sent.")
    else:
        send_email(subject, paths["email"].read_text(encoding="utf-8"), attachments)
        print("Email sent.")
    print(f"Mode: {args.mode}")
    print(f"Stocks: {len(report['stocks'])}")
    print(f"Funds: {len(report['funds'])}")
    print(f"Source counts: {report['source_counts']}")
    if report["errors"]:
        print("Errors:", " | ".join(report["errors"]))
    for name, path in paths.items():
        print(f"{name}: {path.resolve()}")


if __name__ == "__main__":
    main()
