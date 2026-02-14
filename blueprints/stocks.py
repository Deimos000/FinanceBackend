"""
Yahoo Finance proxy blueprint using yfinance.
"""

import requests as http_requests
import yfinance as yf
import pandas as pd
import numpy as np
from flask import Blueprint, request, jsonify

stocks_bp = Blueprint("stocks", __name__)

def _convert_numpy_types(obj):
    """Recursively convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    elif isinstance(obj, (np.floating, float)):
        return float(obj) if not np.isnan(obj) else None
    elif isinstance(obj, (np.ndarray, list, tuple)):
        return [_convert_numpy_types(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: _convert_numpy_types(v) for k, v in obj.items()}
    return obj

@stocks_bp.route("/api/yahoo-proxy", methods=["GET"])
def yahoo_proxy():
    qtype = request.args.get("type", "quote")
    
    # --- SEARCH implementation (unchanged logic but cleaner) ---
    if qtype == "search":
        query_str = request.args.get("query")
        if not query_str:
            return jsonify({"error": "Query param required for search"}), 400
        
        # yfinance doesn't have a direct search API that returns the same structure
        # adhering to reliability requested, we keep using the public API for search 
        # as it's less prone to strict blockage than the chart API, but we use a proper user agent.
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={query_str}&quotesCount=10&newsCount=0"
        try:
            # yfinance uses a session with nice headers, we can try to use standard requests with a fixed user agent
            # or just use the one yfinance uses if accessible, but standard is safer here.
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            resp = http_requests.get(url, headers=headers, timeout=10)
            if not resp.ok:
                 return jsonify({"error": f"Yahoo Search Error: {resp.reason}", "details": resp.text}), resp.status_code
            return jsonify(resp.json())
        except Exception as e:
            return jsonify({"error": "Failed to search stocks", "details": str(e)}), 500

    # --- QUOTE/CHART implementation (via yfinance) ---
    symbol = request.args.get("symbol")
    if not symbol:
        return jsonify({"error": "Symbol param required for quote"}), 400

    interval = request.args.get("interval", "1d")
    rng = request.args.get("range", "1y")

    try:
        print(f"[STOCKS] Fetching data for {symbol}, range={rng}, interval={interval}")
        ticker = yf.Ticker(symbol)
        
        # Fetch history
        hist = ticker.history(period=rng, interval=interval)
        
        if hist.empty:
             print(f"[STOCKS] Empty history for {symbol}")
             return jsonify({"error": "No data found for symbol", "details": "yfinance returned empty history"}), 404

        # Access metadata
        info = ticker.info
        fast_info = ticker.fast_info
        
        print(f"[STOCKS] Info for {symbol}: {info}")
        # fast_info is an object, convert to dict for logging if possible or print repr
        print(f"[STOCKS] FastInfo for {symbol}: {fast_info}")

        # --- Construct API Response matching Yahoo's 'chart' structure ---
        
        # 1. Timestamps (convert from DatetimeIndex to unix timestamp seconds)
        # Use simple list comprehension to be safe against numpy dtype variations
        timestamps = [int(x.timestamp()) for x in hist.index]

        # 2. Indicators (Open, High, Low, Close, Volume)
        quote_indicators = {
            "open": _convert_numpy_types(hist["Open"].values),
            "high": _convert_numpy_types(hist["High"].values),
            "low": _convert_numpy_types(hist["Low"].values),
            "close": _convert_numpy_types(hist["Close"].values),
            "volume": _convert_numpy_types(hist["Volume"].values)
        }

        # 3. Metadata (Meta)
        meta = {
            "symbol": symbol,
            "currency": info.get("currency", "USD"),
            "exchangeName": info.get("exchange", "UNKNOWN"),
            "instrumentType": info.get("quoteType", "EQUITY"),
            "firstTradeDate": info.get("firstTradeDateEpochUtc"),
            "regularMarketTime": info.get("regularMarketTime"),
            "timezone": info.get("timeZoneShortName", "UTC"),
            "exchangeTimezoneName": info.get("exchangeTimezoneName", "America/New_York"),
            "regularMarketPrice": info.get("currentPrice") or fast_info.last_price,
            "chartPreviousClose": info.get("previousClose") or fast_info.previous_close,
            "previousClose": info.get("previousClose") or fast_info.previous_close,
            "scale": 3,
            "priceHint": 2,
            "currentTradingPeriod": {
                "pre": {"timezone": "UTC", "start": 0, "end": 0, "gmtoffset": 0},
                "regular": {"timezone": "UTC", "start": 0, "end": 0, "gmtoffset": 0},
                "post": {"timezone": "UTC", "start": 0, "end": 0, "gmtoffset": 0}
            },
            "dataGranularity": interval,
            "range": rng,
            "validRanges": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]
        }
        
        # Extra fields used by frontend logic:
        meta["longName"] = info.get("longName")
        meta["shortName"] = info.get("shortName")
        meta["regularMarketOpen"] = info.get("open")
        meta["regularMarketDayHigh"] = info.get("dayHigh")
        meta["regularMarketDayLow"] = info.get("dayLow")
        meta["fiftyTwoWeekHigh"] = info.get("fiftyTwoWeekHigh")
        meta["fiftyTwoWeekLow"] = info.get("fiftyTwoWeekLow")

        print(f"[STOCKS] Constructed Meta for {symbol}: {meta}")

        # Construct final structure
        result_obj = {
            "meta": _convert_numpy_types(meta),
            "timestamp": timestamps,
            "indicators": {
                "quote": [quote_indicators]
            }
        }

        response_data = {
            "chart": {
                "result": [result_obj],
                "error": None
            }
        }
        
        return jsonify(response_data)

    except Exception as e:
        print(f"[STOCKS] ERROR for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Failed to fetch stock data via yfinance", "details": str(e)}), 500
