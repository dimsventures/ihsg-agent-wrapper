from flask import Flask, jsonify
import requests
import os
from datetime import datetime

app = Flask(__name__)

ALPHA_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "").strip('"').strip("'")
FRED_KEY  = os.environ.get("FRED_KEY", "").strip('"').strip("'")

# ── Helpers ───────────────────────────────────────────────────────────────────

def alpha_quote(symbol):
    """Equity/ETF quote dari Alpha Vantage."""
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


def frankfurter_rate(from_currency, to_currency):
    """Exchange rate gratis dari Frankfurter — no API key."""
    url = f"https://api.frankfurter.dev/v1/latest?from={from_currency}&to={to_currency}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    rate = data["rates"][to_currency]
    return {
        "close":      round(rate, 4),
        "prev_close": None,
        "change_pct": None,
        "date":       data["date"],
    }


def fred_series(series_id):
    """Ambil nilai terbaru dari FRED."""
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id":  series_id,
        "api_key":    FRED_KEY,
        "file_type":  "json",
        "sort_order": "desc",
        "limit":      2,
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    obs = r.json().get("observations", [])
    if not obs:
        return None
    latest   = obs[0]
    prev     = obs[1] if len(obs) > 1 else obs[0]
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

    # ── FRED: US Macro ────────────────────────────────────────────────────────
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
                errors[name] = "empty data from FRED"
        except Exception as e:
            errors[name] = str(e)

    # ── Frankfurter: Forex gratis ─────────────────────────────────────────────
    forex_targets = {
        "usd_idr": ("USD", "IDR"),
        "usd_jpy": ("USD", "JPY"),
        "eur_usd": ("EUR", "USD"),
    }
    for name, (frm, to) in forex_targets.items():
        try:
            data = frankfurter_rate(frm, to)
            if data:
                result[name] = data
            else:
                errors[name] = "empty data from Frankfurter"
        except Exception as e:
            errors[name] = str(e)

    # ── Alpha Vantage: Equity & Commodity ────────────────────────────────────
    alpha_targets = {
        "gold":  "GLD",
        "sp500": "SPY",
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

    return jsonify({
        "timestamp": datetime.utcnow().isoformat(),
        "data":      result,
        "errors":    errors,
    })


@app.route("/market/macro")
def market_macro():
    """Hanya FRED + Forex — endpoint ringan untuk N8N macro filter."""
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

    # USD/IDR selalu disertakan di macro
    try:
        result["usd_idr"] = frankfurter_rate("USD", "IDR")
    except Exception as e:
        errors["usd_idr"] = str(e)

    return jsonify({
        "timestamp": datetime.utcnow().isoformat(),
        "data":      result,
        "errors":    errors,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
