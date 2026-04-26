from flask import Flask, jsonify
import yfinance as yf
import requests
from requests import Session
from datetime import datetime
import traceback

app = Flask(__name__)

# Session dengan headers supaya tidak diblok Yahoo Finance
def create_session():
    session = Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    })
    return session

TICKERS = {
    "ihsg":    "^JKSE",
    "dxy":     "DX-Y.NYB",
    "gold":    "GC=F",
    "vix":     "^VIX",
    "us10y":   "^TNX",
    "us2y":    "^IRX",
    "sp500":   "^GSPC",
    "usd_idr": "IDR=X",
}

def get_price_data(symbol, period="5d"):
    try:
        session = create_session()
        ticker = yf.Ticker(symbol, session=session)
        hist = ticker.history(period=period)
        if hist.empty:
            return None
        latest = hist.iloc[-1]
        prev   = hist.iloc[-2] if len(hist) >= 2 else hist.iloc[-1]
        close      = round(float(latest["Close"]), 4)
        prev_close = round(float(prev["Close"]), 4)
        change_pct = round((close - prev_close) / prev_close * 100, 2)
        return {
            "close":      close,
            "prev_close": prev_close,
            "change_pct": change_pct,
            "volume":     int(latest.get("Volume", 0)),
            "date":       str(hist.index[-1].date()),
        }
    except Exception as e:
        raise Exception(f"Failed to fetch {symbol}: {str(e)}")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


@app.route("/market/all")
def market_all():
    result, errors = {}, {}
    for name, symbol in TICKERS.items():
        try:
            data = get_price_data(symbol)
            if data:
                result[name] = data
            else:
                errors[name] = "empty data"
        except Exception as e:
            errors[name] = str(e)
    return jsonify({
        "timestamp": datetime.utcnow().isoformat(),
        "data":      result,
        "errors":    errors,
    })


@app.route("/market/<ticker_name>")
def market_single(ticker_name):
    if ticker_name not in TICKERS:
        return jsonify({"error": f"Unknown ticker '{ticker_name}'"}), 404
    try:
        data = get_price_data(TICKERS[ticker_name])
        if not data:
            return jsonify({"error": "No data returned"}), 502
        return jsonify({"ticker": ticker_name, **data})
    except Exception as e:
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/market/ihsg/history")
def ihsg_history():
    try:
        session = create_session()
        ticker = yf.Ticker("^JKSE", session=session)
        hist   = ticker.history(period="1mo")
        rows   = []
        for date, row in hist.iterrows():
            rows.append({
                "date":  str(date.date()),
                "close": round(float(row["Close"]), 2),
            })
        return jsonify({"data": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
