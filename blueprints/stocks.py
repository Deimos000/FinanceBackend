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
    
    if qtype == "market_movers":
        # Curated list of high-cap stocks to simulate a screener
        tickers = [
            "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA",
            "AMD", "AVGO", "ORCL", "CRM", "ADBE", "NFLX", "INTC",
            "QCOM", "TXN", "IBM", "CSCO", "UBER", "ABNB", "PYPL",
            "SQ", "COIN", "SHOP", "SPOT", "SNOW", "PLTR", "U", "RBLX",
            "DKNG", "NET", "CRWD", "DDOG", "ZS", "TEAM", "MDB"
        ]
        
        try:
            # Efficiently fetch multiple tickers at once
            data = yf.Tickers(" ".join(tickers))
            results = []
            
            for symbol in tickers:
                try:
                    info = data.tickers[symbol].info
                    # Fallback to fast_info if info is missing or slow
                    fast_info = data.tickers[symbol].fast_info
                    
                    price = info.get("currentPrice") or fast_info.last_price
                    prev_close = info.get("previousClose") or fast_info.previous_close
                    
                    if price and prev_close:
                        change = price - prev_close
                        change_percent = (change / prev_close) * 100
                        
                        # Only include if Market Cap > 300M (using 30B here as realistic "High Cap" filter for this list, but list is already curated)
                        mcap = info.get("marketCap")
                        
                        results.append({
                            "symbol": symbol,
                            "name": info.get("shortName") or symbol,
                            "price": price,
                            "change": change,
                            "changePercent": change_percent,
                            "marketCap": mcap
                        })
                except Exception as e:
                    # Skip failures for individual tickers
                    continue
            
            # Sort by absolute change percent desc (Movers) OR just Top Gainers
            # User asked for "Highest Change" imply Gainers usually, or volatility. 
            # Let's sort by Change Percent Descending (Top Gainers)
            results.sort(key=lambda x: x["changePercent"], reverse=True)
            
            return jsonify({"quotes": results[:10]})
            
        except Exception as e:
            return jsonify({"error": "Failed to fetch market movers", "details": str(e)}), 500

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
    start_date = request.args.get("start")
    end_date = request.args.get("end")

    try:
        print(f"[STOCKS] Fetching data for {symbol}, range={rng}, interval={interval}, start={start_date}, end={end_date}")
        ticker = yf.Ticker(symbol)
        
        # Fetch history
        if start_date and end_date:
            hist = ticker.history(start=start_date, end=end_date, interval=interval)
        else:
            hist = ticker.history(period=rng, interval=interval)
        
        if hist.empty:
             print(f"[STOCKS] Empty history for {symbol}")
             return jsonify({"error": "No data found for symbol", "details": "yfinance returned empty history"}), 404

        # Access metadata
        info = ticker.info
        fast_info = ticker.fast_info
        
        # --- Construct API Response matching Yahoo's 'chart' structure ---
        
        # Snapshot logic: if we have a custom range, overwrite "current" values with the last available bar in that range
        is_historical = bool(start_date and end_date)
        snapshot_date = None
        
        current_price = info.get("currentPrice") or fast_info.last_price
        prev_close = info.get("previousClose") or fast_info.previous_close
        reg_open = info.get("open")
        reg_high = info.get("dayHigh")
        reg_low = info.get("dayLow")
        reg_volume = info.get("volume") or info.get("regularMarketVolume")

        if is_historical and not hist.empty:
            last_bar = hist.iloc[-1]
            current_price = _convert_numpy_types(last_bar["Close"])
            reg_open = _convert_numpy_types(last_bar["Open"])
            reg_high = _convert_numpy_types(last_bar["High"])
            reg_low = _convert_numpy_types(last_bar["Low"])
            reg_volume = _convert_numpy_types(last_bar["Volume"])
            snapshot_date = str(hist.index[-1].date())
            
            if len(hist) > 1:
                prev_close = _convert_numpy_types(hist.iloc[-2]["Close"])

        # 1. Timestamps (convert from DatetimeIndex to unix timestamp seconds)
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
            "regularMarketPrice": current_price,
            "chartPreviousClose": prev_close,
            "previousClose": prev_close,
            "scale": 3,
            "priceHint": 2,
            "currentTradingPeriod": {
                "pre": {"timezone": "UTC", "start": 0, "end": 0, "gmtoffset": 0},
                "regular": {"timezone": "UTC", "start": 0, "end": 0, "gmtoffset": 0},
                "post": {"timezone": "UTC", "start": 0, "end": 0, "gmtoffset": 0}
            },
            "dataGranularity": interval,
            "range": rng,
            "validRanges": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"],
            "snapshotDate": snapshot_date
        }
        
        # Extra fields used by frontend logic:
        meta["longName"] = info.get("longName")
        meta["shortName"] = info.get("shortName")
        meta["regularMarketOpen"] = reg_open
        meta["regularMarketDayHigh"] = reg_high
        meta["regularMarketDayLow"] = reg_low
        meta["fiftyTwoWeekHigh"] = info.get("fiftyTwoWeekHigh")
        meta["fiftyTwoWeekLow"] = info.get("fiftyTwoWeekLow")
        meta["marketCap"] = info.get("marketCap")
        meta["volume"] = reg_volume
        meta["trailingPE"] = info.get("trailingPE")
        meta["dividendYield"] = info.get("dividendYield") or info.get("trailingAnnualDividendYield")
        meta["sector"] = info.get("sector")
        meta["industry"] = info.get("industry")
        meta["fullTimeEmployees"] = info.get("fullTimeEmployees")
        meta["website"] = info.get("website")
        meta["city"] = info.get("city")
        meta["country"] = info.get("country")
        meta["longBusinessSummary"] = info.get("longBusinessSummary")
        
        # New Rework Fields:
        # Analyst Ratings
        meta["recommendationKey"] = info.get("recommendationKey")
        meta["recommendationMean"] = info.get("recommendationMean")
        meta["numberOfAnalystOpinions"] = info.get("numberOfAnalystOpinions")
        meta["targetHighPrice"] = info.get("targetHighPrice")
        meta["targetLowPrice"] = info.get("targetLowPrice")
        meta["targetMeanPrice"] = info.get("targetMeanPrice")
        meta["targetMedianPrice"] = info.get("targetMedianPrice")
        
        # Financial Ratios
        meta["forwardPE"] = info.get("forwardPE")
        meta["priceToBook"] = info.get("priceToBook")
        meta["priceToSalesTrailing12Months"] = info.get("priceToSalesTrailing12Months")
        meta["enterpriseToEbitda"] = info.get("enterpriseToEbitda")
        meta["trailingPegRatio"] = info.get("trailingPegRatio")
        meta["profitMargins"] = info.get("profitMargins")
        meta["grossMargins"] = info.get("grossMargins")
        meta["operatingMargins"] = info.get("operatingMargins")
        meta["ebitdaMargins"] = info.get("ebitdaMargins")
        meta["returnOnAssets"] = info.get("returnOnAssets")
        meta["returnOnEquity"] = info.get("returnOnEquity")
        meta["revenueGrowth"] = info.get("revenueGrowth")
        meta["earningsGrowth"] = info.get("earningsGrowth")
        meta["forwardEps"] = info.get("forwardEps")
        meta["payoutRatio"] = info.get("payoutRatio")
        
        # Financial Health
        meta["totalCash"] = info.get("totalCash")
        meta["totalDebt"] = info.get("totalDebt")
        meta["currentRatio"] = info.get("currentRatio")
        meta["quickRatio"] = info.get("quickRatio")
        meta["freeCashflow"] = info.get("freeCashflow")
        meta["operatingCashflow"] = info.get("operatingCashflow")
        meta["ebitda"] = info.get("ebitda")
        
        # Market Data / Ownership
        meta["beta"] = info.get("beta")
        meta["heldPercentInsiders"] = info.get("heldPercentInsiders")
        meta["heldPercentInstitutions"] = info.get("heldPercentInstitutions")
        meta["shortRatio"] = info.get("shortRatio")
        meta["shortPercentOfFloat"] = info.get("shortPercentOfFloat")
        meta["sharesOutstanding"] = info.get("sharesOutstanding")
        meta["floatShares"] = info.get("floatShares")
        
        # Company Officers
        meta["companyOfficers"] = info.get("companyOfficers")
        
        # Governance
        meta["overallRisk"] = info.get("overallRisk")
        meta["auditRisk"] = info.get("auditRisk")
        meta["boardRisk"] = info.get("boardRisk")
        meta["compensationRisk"] = info.get("compensationRisk")

        print(f"[STOCKS] Constructed Meta for {symbol}: {meta}")

        # Construction final structure
        result_obj = {
            "meta": _convert_numpy_types(meta),
            "timestamp": timestamps,
            "indicators": {
                "quote": [quote_indicators]
            }
        }

        # --- EXTRAS: Historical Comparison Data ---
        comparison = {"years": [], "metrics": {}}
        try:
            # Fetch all three statements
            financials = ticker.financials
            balance_sheet = ticker.balance_sheet
            cashflow = ticker.cashflow
            
            if not financials.empty:
                # Get the last 2 fiscal years (columns are dates)
                cols = financials.columns[:2]
                comparison["years"] = [str(c.year) for c in cols]
                
                def get_metric(df, names):
                    """Try multiple possible names for a metric."""
                    if df is None or df.empty: return [None, None]
                    if isinstance(names, str): names = [names]
                    for name in names:
                        if name in df.index:
                            return [_convert_numpy_types(v) for v in df.loc[name, cols].values]
                    return [None, None]

                # Income Statement
                comparison["metrics"]["totalRevenue"] = get_metric(financials, ["Total Revenue", "Total Operating Revenue"])
                comparison["metrics"]["grossProfit"] = get_metric(financials, "Gross Profit")
                comparison["metrics"]["operatingIncome"] = get_metric(financials, "Operating Income")
                comparison["metrics"]["ebitda"] = get_metric(financials, "EBITDA")
                comparison["metrics"]["netIncome"] = get_metric(financials, ["Net Income", "Net Income Common Stockholders"])
                comparison["metrics"]["basicEPS"] = get_metric(financials, ["Basic EPS", "Basic Earnings Per Share", "Basic EPS Common Stockholders"])
                comparison["metrics"]["dilutedEPS"] = get_metric(financials, ["Diluted EPS", "Diluted Earnings Per Share", "Diluted EPS Common Stockholders"])
                
                # Balance Sheet
                if not balance_sheet.empty:
                    comparison["metrics"]["totalAssets"] = get_metric(balance_sheet, "Total Assets")
                    comparison["metrics"]["totalLiabilities"] = get_metric(balance_sheet, ["Total Liabilities Net Minority Interest", "Total Liabilities"])
                    comparison["metrics"]["equity"] = get_metric(balance_sheet, "Stockholders Equity")
                    comparison["metrics"]["totalCash"] = get_metric(balance_sheet, ["Cash And Cash Equivalents", "Cash Financial", "Cash Cash Equivalents And Short Term Investments"])
                    comparison["metrics"]["totalDebt"] = get_metric(balance_sheet, "Total Debt")
                    comparison["metrics"]["inventory"] = get_metric(balance_sheet, "Inventory")

                # Cash Flow
                if not cashflow.empty:
                    comparison["metrics"]["operatingCashflow"] = get_metric(cashflow, "Operating Cash Flow")
                    comparison["metrics"]["investingCashflow"] = get_metric(cashflow, "Investing Cash Flow")
                    comparison["metrics"]["financingCashflow"] = get_metric(cashflow, "Financing Cash Flow")
                    comparison["metrics"]["freeCashflow"] = get_metric(cashflow, "Free Cash Flow")

            result_obj["comparison"] = comparison
        except Exception as fe:
            print(f"[STOCKS] Failed to fetch financials for {symbol}: {fe}")

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
