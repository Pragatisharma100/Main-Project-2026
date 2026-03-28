"""
AKS Wealthply — VCP Scanner Backend
Flask + yfinance | EOD Data | Custom Scanner Support
Run: python vcp_scanner.py
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import numpy as np
import json, os, time
from datetime import datetime, timedelta
from pathlib import Path

app = Flask(__name__)
CORS(app)

# ── Folders ───────────────────────────────────────────────────
DATA_DIR   = Path("data")          # cached OHLCV JSON files
RESULT_DIR = Path("results")       # scan result JSON files
DATA_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

# ── Scan progress (shared state) ─────────────────────────────
scan_state = {
    "running": False,
    "progress": 0,
    "total": 0,
    "log": [],
    "scanner_id": None
}

# ═══════════════════════════════════════════════════════════════
# DATA FETCHING — yfinance
# ═══════════════════════════════════════════════════════════════
def fetch_stock_data(symbol: str, end_date: str, period: str = "1y") -> pd.DataFrame | None:
    """Improved fetch with retry, delay, and better error handling for NSE stocks"""
    cache_file = DATA_DIR / f"{symbol}_{end_date}.json"

    # Use cache if fresh
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < 21600:  # 6 hours
            try:
                df = pd.read_json(cache_file)
                df.index = pd.to_datetime(df.index)
                return df
            except:
                pass

    nse_symbol = symbol if "." in symbol else f"{symbol}.NS"
    
    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    if period == "6mo":
        days_back = 183
    elif period == "2y":
        days_back = 730
    else:
        days_back = 365
    start_dt = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=days_back)

    max_retries = 4
    for attempt in range(max_retries):
        try:
            print(f"  Fetching {symbol} (attempt {attempt+1})...")
            ticker = yf.Ticker(nse_symbol)
            df = ticker.history(
                start=start_dt.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
                interval="1d",
                auto_adjust=True,
                timeout=15
            )

            if not df.empty and len(df) >= 60:
                df.index = df.index.strftime("%Y-%m-%d")
                df.to_json(cache_file)
                df.index = pd.to_datetime(df.index)
                print(f"  ✅ {symbol} — {len(df)} days loaded")
                return df

            time.sleep(1.2)  # small delay

        except Exception as e:
            error_str = str(e).lower()
            if "rate limit" in error_str or "too many requests" in error_str:
                print(f"  ⏳ Rate limit hit for {symbol}, waiting longer...")
                time.sleep(8)   # longer wait on rate limit
            else:
                print(f"  ✗ {symbol}: {str(e)[:120]}")
            
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # exponential backoff
            else:
                print(f"  ❌ Failed to fetch {symbol} after {max_retries} attempts")

    return None

# ═══════════════════════════════════════════════════════════════
# VCP ENGINE — Core calculation
# ═══════════════════════════════════════════════════════════════

def calc_atr(df: pd.DataFrame, period: int) -> float | None:
    """Average True Range"""
    if len(df) < period + 1:
        return None
    highs  = df["High"].values
    lows   = df["Low"].values
    closes = df["Close"].values
    trs = []
    for i in range(1, len(df)):
        tr = max(
            highs[i]  - lows[i],
            abs(highs[i]  - closes[i-1]),
            abs(lows[i]   - closes[i-1])
        )
        trs.append(tr)
    trs = trs[-period:]
    return round(float(np.mean(trs)), 2)


def run_vcp(symbol: str, df: pd.DataFrame, cfg: dict) -> dict | None:
    """
    Run VCP conditions on a DataFrame.
    cfg = scanner config from localStorage (conditions + thresholds).
    Returns result dict or None if score < minScore.
    """
    closes  = df["Close"].values
    highs   = df["High"].values
    lows    = df["Low"].values
    volumes = df["Volume"].values
    dates   = df.index.strftime("%Y-%m-%d").tolist()
    n = len(closes)

    if n < 60:
        print(f"  ✗ {symbol} — not enough historical data ({n} days)")
        return None

    # ── Moving Averages ──────────────────────────────────────
    def sma(arr, period, idx):
        if idx < period - 1:
            return None
        return float(np.mean(arr[idx - period + 1: idx + 1]))

    last    = float(closes[-1])
    ma20    = sma(closes, 20,  n-1)
    ma50    = sma(closes, 50,  n-1)
    ma200   = sma(closes, 200, n-1)
    ma50_20 = sma(closes, 50,  n-21) if n >= 71 else None

    # ── Condition 1: UPTREND ─────────────────────────────────
    cond_cfg   = cfg.get("conditions", {})
    use_uptrend = cond_cfg.get("uptrend", {}).get("active", True)
    cond1 = True
    c1_detail = "Skipped"
    if use_uptrend and ma50 and ma200:
        above50  = last > ma50
        above200 = last > ma200
        ma50_up  = (ma50 > ma50_20) if ma50_20 else False
        cond1 = above50 and above200 and ma50_up
        c1_detail = (
            f"Price ₹{last:.1f} > MA50 ₹{ma50:.1f} ({'✓' if above50 else '✗'}) "
            f"> MA200 ₹{ma200:.1f} ({'✓' if above200 else '✗'}), "
            f"MA50 trend {'↑ Rising' if ma50_up else '↓ Flat'}"
        )
    elif not use_uptrend:
        cond1 = True
        c1_detail = "Condition disabled"

    # ── ATR values ───────────────────────────────────────────
    atr10_now  = calc_atr(df, 10)
    atr10_40   = calc_atr(df.iloc[:-40], 10) if n >= 60 else None
    atr20_now  = calc_atr(df, 20)

    # ── Condition 2: ATR CONTRACTION ────────────────────────
    use_atr     = cond_cfg.get("atr", {}).get("active", True)
    atr_thresh  = cond_cfg.get("atr", {}).get("threshold", 80) / 100
    cond2 = True
    c2_detail = "Skipped"
    if use_atr and atr10_now and atr10_40:
        ratio = atr10_now / atr10_40
        cond2 = ratio < atr_thresh
        c2_detail = (
            f"ATR(10) now ₹{atr10_now} vs 40d ago ₹{atr10_40} "
            f"= {ratio*100:.1f}% (need <{atr_thresh*100:.0f}%)"
        )
    elif not use_atr:
        cond2 = True
        c2_detail = "Condition disabled"

    # ── Volume ───────────────────────────────────────────────
    avg_vol50 = float(np.mean(volumes[-50:-1])) if n >= 51 else float(np.mean(volumes))
    avg_vol10 = float(np.mean(volumes[-10:]))
    vol_ratio = round(avg_vol10 / avg_vol50, 2) if avg_vol50 > 0 else 1.0

    # ── Condition 3: VOLUME DRY-UP ───────────────────────────
    use_vol    = cond_cfg.get("vol", {}).get("active", True)
    vol_thresh = cond_cfg.get("vol", {}).get("threshold", 80) / 100
    cond3 = True
    c3_detail = "Skipped"
    if use_vol:
        cond3 = vol_ratio < vol_thresh
        c3_detail = (
            f"Vol(10d) {avg_vol10/1e5:.1f}L vs Vol(50d) {avg_vol50/1e5:.1f}L "
            f"= {vol_ratio*100:.1f}% (need <{vol_thresh*100:.0f}%)"
        )
    else:
        cond3 = True
        c3_detail = "Condition disabled"

    # ── Range ────────────────────────────────────────────────
    ranges_10 = [highs[i] - lows[i] for i in range(n-10, n)]
    ranges_50 = [highs[i] - lows[i] for i in range(n-50, n)]
    avg_r10 = float(np.mean(ranges_10))
    avg_r50 = float(np.mean(ranges_50))

    # ── Condition 4: RANGE TIGHTENING ───────────────────────
    use_range    = cond_cfg.get("range", {}).get("active", True)
    range_thresh = cond_cfg.get("range", {}).get("threshold", 75) / 100
    cond4 = True
    c4_detail = "Skipped"
    if use_range and avg_r50 > 0:
        rr = avg_r10 / avg_r50
        cond4 = rr < range_thresh
        c4_detail = (
            f"Range(10d) ₹{avg_r10:.2f} vs Range(50d) ₹{avg_r50:.2f} "
            f"= {rr*100:.1f}% (need <{range_thresh*100:.0f}%)"
        )
    elif not use_range:
        cond4 = True
        c4_detail = "Condition disabled"

    # ── Condition 5: NEAR PIVOT ──────────────────────────────
    lb = min(n, 130)
    pivot_high  = float(np.max(highs[-lb:]))
    from_pivot  = round((pivot_high - last) / pivot_high * 100, 2)
    use_pivot   = cond_cfg.get("pivot", {}).get("active", False)
    pivot_thresh = cond_cfg.get("pivot", {}).get("threshold", 10)
    cond5 = True
    if use_pivot:
        cond5 = from_pivot <= pivot_thresh

    # ── Condition 6: NEAR 52W HIGH ───────────────────────────
    lb52 = min(n, 252)
    high_52w = float(np.max(highs[-lb52:]))
    low_52w  = float(np.min(lows[-lb52:]))
    from_52w = round((high_52w - last) / high_52w * 100, 2)
    use_52w  = cond_cfg.get("52w", {}).get("active", False)
    w52_thresh = cond_cfg.get("52w", {}).get("threshold", 20)
    cond6 = True
    if use_52w:
        cond6 = from_52w <= w52_thresh

    # ── Score ─────────────────────────────────────────────────
    active_conds = []
    if use_uptrend: active_conds.append(cond1)
    if use_atr:     active_conds.append(cond2)
    if use_vol:     active_conds.append(cond3)
    if use_range:   active_conds.append(cond4)
    if use_pivot:   active_conds.append(cond5)
    if use_52w:     active_conds.append(cond6)

    total_active = len(active_conds)
    score_raw    = sum(active_conds)
    # Normalise to 4 for display
    score = score_raw if total_active <= 4 else round(score_raw / total_active * 4)

    min_score = cfg.get("minScore", 2)
    print(f"  {symbol} raw score: {score_raw}/{total_active}")
    if score_raw < min_score:
        return None

    # ── Breakout ─────────────────────────────────────────────
    breakout = (from_pivot < 3) and (volumes[-1] > avg_vol50 * 1.5)

    # ── Signal label ─────────────────────────────────────────
    if score_raw == total_active and breakout:
        signal = "STRONG BUY — Breakout!"
    elif score_raw == total_active:
        signal = "STRONG BUY"
    elif score_raw >= total_active * 0.75:
        signal = "BUY SETUP"
    elif score_raw >= total_active * 0.5:
        signal = "WATCH"
    else:
        signal = "DEVELOPING"

    # ── Change % ─────────────────────────────────────────────
    change_pct = round((last - closes[-2]) / closes[-2] * 100, 2) if n > 1 else 0

    # ── OHLCV bars for chart ──────────────────────────────────
    bars = [
        {
            "date":   dates[i],
            "open":   round(float(df["Open"].values[i]),  2),
            "high":   round(float(df["High"].values[i]),  2),
            "low":    round(float(df["Low"].values[i]),   2),
            "close":  round(float(df["Close"].values[i]), 2),
            "volume": int(df["Volume"].values[i])
        }
        for i in range(len(df))
    ]

    return {
        "symbol":         symbol,
        "name":           symbol,
        "price":          round(last, 2),
        "change_pct":     change_pct,
        "ma20":           round(ma20,  2) if ma20  else 0,
        "ma50":           round(ma50,  2) if ma50  else 0,
        "ma200":          round(ma200, 2) if ma200 else 0,
        "atr10":          atr10_now or 0,
        "atr20":          atr20_now or 0,
        "vol_ratio":      vol_ratio,
        "pivot_high":     round(pivot_high, 2),
        "from_pivot":     from_pivot,
        "high_52w":       round(high_52w, 2),
        "low_52w":        round(low_52w,  2),
        "from_52w":       from_52w,
        "score":          score,
        "score_raw":      score_raw,
        "total_conditions": total_active,
        "signal":         signal,
        "breakout":       breakout,
        "cond1_uptrend":  cond1,
        "cond2_atr":      cond2,
        "cond3_volume":   cond3,
        "cond4_range":    cond4,
        "cond5_pivot":    cond5,
        "cond6_52w":      cond6,
        "c1_detail":      c1_detail,
        "c2_detail":      c2_detail,
        "c3_detail":      c3_detail,
        "c4_detail":      c4_detail,
        "tv_link":        f"https://www.tradingview.com/chart/?symbol=NSE:{symbol}",
        "bars":           bars
    }


# ═══════════════════════════════════════════════════════════════
# SCAN RUNNER — processes watchlist with given scanner config
# ═══════════════════════════════════════════════════════════════

import threading

def run_scan_thread(symbols: list, end_date: str, period: str, cfg: dict, scanner_id: str):
    """Runs in background thread. Updates scan_state live."""
    global scan_state
    scan_state.update({
        "running": True,
        "progress": 0,
        "total": len(symbols),
        "log": [f"📅 Scan date: {end_date} | {len(symbols)} stocks"],
        "scanner_id": scanner_id
    })

    results = []
    for i, sym in enumerate(symbols):
        if not scan_state["running"]:
            break

        scan_state["log"].append(f"⟳ Fetching {sym}...")
        df = fetch_stock_data(sym, end_date, period)

        if df is None or len(df) < 60:
            scan_state["log"].append(f"✗ {sym} — no data or insufficient history")
        else:
            scan_state["log"].append(f"✓ {sym} — {len(df)} days data loaded, running VCP...")
            r = run_vcp(sym, df, cfg)
            if r:
                results.append(r)
                scan_state["log"].append(
                    f"✅ {sym} — Score {r['score_raw']}/{r['total_conditions']} | {r['signal']}"
                )
            else:
                scan_state["log"].append(f"— {sym} — below min score or conditions not met")

        scan_state["progress"] = i + 1
        if len(scan_state["log"]) > 60:
            scan_state["log"] = scan_state["log"][-60:]

    # Sort results
    results.sort(key=lambda x: (-x["score_raw"], -int(x.get("breakout", False))))

    # Save results to file
    result_file = RESULT_DIR / f"{scanner_id}_{end_date}.json"
    with open(result_file, "w") as f:
        json.dump({
            "scanner_id": scanner_id,
            "end_date":   end_date,
            "scanned_at": datetime.now().isoformat(),
            "total":      len(symbols),
            "matched":    len(results),
            "results":    results
        }, f)

    scan_state["running"]  = False
    scan_state["log"].append(
        f"✓ Done! {len(results)}/{len(symbols)} stocks matched."
    )


# ═══════════════════════════════════════════════════════════════
# FLASK API ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route("/api/scan", methods=["POST"])
def api_scan():
    """
    POST /api/scan
    Body: { symbols:[...], end_date:"YYYY-MM-DD", period:"1y",
            scanner_id:"...", config:{...} }
    Starts background scan thread.
    """
    if scan_state["running"]:
        return jsonify({"error": "Scan already running"}), 409

    data       = request.get_json(force=True)
    symbols    = [s.strip().upper() for s in data.get("symbols", []) if s.strip()]
    end_date   = data.get("end_date", datetime.now().strftime("%Y-%m-%d"))
    period     = data.get("period",   "1y")
    scanner_id = data.get("scanner_id", "default")
    cfg        = data.get("config", {})

    if not symbols:
        return jsonify({"error": "No symbols provided"}), 400

    t = threading.Thread(
        target=run_scan_thread,
        args=(symbols, end_date, period, cfg, scanner_id),
        daemon=True
    )
    t.start()
    return jsonify({"started": True, "total": len(symbols)})


@app.route("/api/progress")
def api_progress():
    """GET /api/progress — live scan progress"""
    return jsonify({
        "running":    scan_state["running"],
        "progress":   scan_state["progress"],
        "total":      scan_state["total"],
        "log":        scan_state["log"][-20:],
        "scanner_id": scan_state["scanner_id"]
    })


@app.route("/api/results")
def api_results():
    """
    GET /api/results?scanner_id=xxx&end_date=YYYY-MM-DD
    Returns latest result file for given scanner.
    """
    scanner_id = request.args.get("scanner_id", "default")
    end_date   = request.args.get("end_date", "")

    # Find matching result file
    if end_date:
        f = RESULT_DIR / f"{scanner_id}_{end_date}.json"
        if f.exists():
            return jsonify(json.loads(f.read_text()))
        return jsonify({"results": [], "matched": 0, "error": "No result for this date"})

    # Return most recent file for this scanner
    files = sorted(RESULT_DIR.glob(f"{scanner_id}_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    if files:
        return jsonify(json.loads(files[0].read_text()))
    return jsonify({"results": [], "matched": 0})


@app.route("/api/chart/<symbol>")
def api_chart(symbol):
    """
    GET /api/chart/RELIANCE?end_date=YYYY-MM-DD&period=1y
    Returns OHLCV bars for chart rendering.
    """
    end_date = request.args.get("end_date", datetime.now().strftime("%Y-%m-%d"))
    period   = request.args.get("period",   "1y")
    df = fetch_stock_data(symbol.upper(), end_date, period)
    if df is None:
        return jsonify({"error": "No data"}), 404

    bars = [
        {
            "date":   df.index[i].strftime("%Y-%m-%d"),
            "open":   round(float(df["Open"].values[i]),  2),
            "high":   round(float(df["High"].values[i]),  2),
            "low":    round(float(df["Low"].values[i]),   2),
            "close":  round(float(df["Close"].values[i]), 2),
            "volume": int(df["Volume"].values[i])
        }
        for i in range(len(df))
    ]
    return jsonify({"symbol": symbol, "bars": bars, "count": len(bars)})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """POST /api/stop — abort running scan"""
    scan_state["running"] = False
    return jsonify({"stopped": True})


@app.route("/api/clear_cache", methods=["POST"])
def api_clear_cache():
    """POST /api/clear_cache — delete old data files"""
    deleted = 0
    cutoff  = time.time() - 86400  # older than 1 day
    for f in DATA_DIR.glob("*.json"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            deleted += 1
    return jsonify({"deleted": deleted})


@app.route("/api/health")
def api_health():
    return jsonify({
        "status":   "ok",
        "version":  "2.0",
        "scanning": scan_state["running"]
    })


# ─── CORS preflight ──────────────────────────────────────────
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

# ====================== SERVE HTML FILES ======================

@app.route("/")
def serve_index():
    try:
        return open("index.html", encoding="utf-8").read()
    except FileNotFoundError:
        return "index.html not found. Please make sure all HTML files are in the same folder as vcp_scanner.py", 404

@app.route("/scanner.html")
def serve_scanner():
    try:
        return open("scanner.html", encoding="utf-8").read()
    except FileNotFoundError:
        return "scanner.html not found", 404

@app.route("/scanner-builder.html")
def serve_builder():
    try:
        return open("scanner-builder.html", encoding="utf-8").read()
    except FileNotFoundError:
        return "scanner-builder.html not found", 404

@app.route("/my-scanners.html")
def serve_my_scanners():
    try:
        return open("my-scanners.html", encoding="utf-8").read()
    except FileNotFoundError:
        return "my-scanners.html not found", 404

# Optional: Serve any other static files (css, js, etc.) if needed later
@app.route("/<path:filename>")
def serve_static(filename):
    try:
        return open(filename, encoding="utf-8").read()
    except:
        return "File not found", 404


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  AKS Wealthply — VCP Scanner Backend  ")
    print("=" * 60)
    print(f"  Data cache  : {DATA_DIR.resolve()}")
    print(f"  Results     : {RESULT_DIR.resolve()}")
    print(f"  API URL     : http://localhost:5000")
    print(f"  Web UI      : http://localhost:5000")
    print("=" * 60)
    print("All HTML files should be in the same folder as this script.")
    app.run(host="0.0.0.0", port=5000, debug=False)