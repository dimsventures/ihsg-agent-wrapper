from flask import Flask, jsonify
import requests
import os
from datetime import datetime

app = Flask(__name__)

ALPHA_KEY = os.environ.get("10S3WO1UJULSIR4K")
FRED_KEY  = os.environ.get("8441939bdde9fabd12e1b43a5f21b272")

# ── Helpers ───────────────────────────────────────────────────────────────────

def alpha_quote(symbol):
    """Global quote dari Alpha Vantage."""
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol":   symbol,
        "apikey":   ALPHA_KEY,
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json().get("Global Quote", {})
    if not data or not data.get("05. price"):
        return None
    close      = round(float(data["05. price"]), 4)
    prev_close = round(float(data["08. previous close"]), 4)
    change_pct = round(float(data["10. change percent"].replace("%", "")), 2)
    return {
        "close":      close,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "volume":     int(float(data.get("06. volume", 0))),
        "date":       data.get("07. latest trading day", ""),
    }


def alpha_forex(from_currency, to_currency):
    """Exchange rate dari Alpha Vantage."""
    url = "https://www.alphavantage.co/query"
    params = {
        "function":      "CURRENCY_EXCHANGE_RATE",
        "from_currency": from_currency,
        "to_currency":   to_currency,
        "apikey":        ALPHA_KEY,
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json().get("Realtime Currency Exchange Rate", {})
    if not data:
        return None
    rate = round(float(data["5. Exchange Rate"]), 4)
    return {
        "close":      rate,
        "prev_close": None,
        "change_pct": None,
        "date":       data.get("6. Last Refreshed", ""),
    }


def fred_series(series_id):
    """Ambil nilai terbaru dari FRED."""
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id":      series_id,
        "api_key":        FRED_KEY,
        "file_type":      "json",
        "sort_order":     "desc",
        "limit":          2,
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    obs = r.json().get("observations", [])
    if not obs:
        return None
    latest = obs[0]
    prev   = obs[1] if len(obs) > 1 else obs[0]
    val      = float(latest["value"])
    prev_val = float(prev["value"])
    change_pct = round((val - prev_val) / prev_val * 100, 4) if prev_val else None
    return {
        "close":      round(val, 4),
        "prev_close": round(prev_val, 4),
        "change_pct": change_pct,
        "date":       latest["date"],
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({
        "status":    "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "alpha_key": "set" if ALPHA_KEY else "MISSING",
        "fred_key":  "set" if FRED_KEY  else "MISSING",
    })


@app.route("/market/all")
def market_all():
    result, errors = {}, {}

    # ── Alpha Vantage: equity & commodity ────────────────────────────────────
    alpha_targets = {
        "ihsg":  "JKSE",      # Jakarta Composite
        "sp500": "SPY",       # S&P 500 proxy ETF
        "gold":  "GLD",       # Gold ETF proxy
    }
    for name, symbol in alpha_targets.items():
        try:
            data = alpha_quote(symbol)
            if data:
                result[name] = data
            else:
                errors[name] = "empty data from Alpha Vantage"
        except Exception as e:
            errors[name] = str(e)

    # ── Alpha Vantage: Forex ──────────────────────────────────────────────────
    try:
        usd_idr = alpha_forex("USD", "IDR")
        if usd_idr:
            result["usd_idr"] = usd_idr
        else:
            errors["usd_idr"] = "empty data"
    except Exception as e:
        errors["usd_idr"] = str(e)

    # ── FRED: macro indicators ────────────────────────────────────────────────
    fred_targets = {
        "fed_rate": "FEDFUNDS",   # Fed Funds Rate
        "us10y":    "DGS10",      # 10Y Treasury
        "us2y":     "DGS2",       # 2Y Treasury
        "walcl":    "WALCL",      # Fed Balance Sheet
        "m2_us":    "M2SL",       # US M2
        "cpi":      "CPIAUCSL",   # CPI
        "nfp":      "PAYEMS",     # Non-Farm Payroll
        "dxy":      "DTWEXBGS",   # DXY proxy (broad dollar index)
    }
    for name, series_id in fred_targets.items():
        try:
            data = fred_series(series_id)
            if data:
                result[name] = data
            else:
                errors[name] = "empty data from FRED"
        except Exception as e:
            errors[name] = str(e)

    return jsonify({
        "timestamp": datetime.utcnow().isoformat(),
        "data":      result,
        "errors":    errors,
    })


@app.route("/market/macro")
def market_macro():
    """Hanya FRED data — untuk N8N macro filter node."""
    result, errors = {}, {}
    fred_targets = {
        "fed_rate": "FEDFUNDS",
        "us10y":    "DGS10",
        "us2y":     "DGS2",
        "walcl":    "WALCL",
        "m2_us":    "M2SL",
        "cpi":      "CPIAUCSL",
        "nfp":      "PAYEMS",
        "dxy":      "DTWEXBGS",
    }
    for name, series_id in fred_targets.items():
        try:
            data = fred_series(series_id)
            if data:
                result[name] = data
            else:
                errors[name] = "empty"
        except Exception as e:
            errors[name] = str(e)
    return jsonify({"timestamp": datetime.utcnow().isoformat(), "data": result, "errors": errors})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
