
import yfinance as yf
import pandas as pd
import numpy as np

def test_conversion():
    symbol = "AAPL"
    print(f"Fetching {symbol}...")
    ticker = yf.Ticker(symbol)
    
    # Test 1d range (intraday 15m)
    print("\n--- 1d / 15m ---")
    hist = ticker.history(period="1d", interval="15m")
    if hist.empty:
        print("Empty history")
    else:
        print("Index dtype:", hist.index.dtype)
        print("First index val:", hist.index[0])
        try:
            timestamps = (hist.index.astype('int64') // 10**9).tolist()
            print("First timestamp (sec):", timestamps[0])
            print("First timestamp (date):", pd.to_datetime(timestamps[0], unit='s'))
        except Exception as e:
            print("Conversion failed:", e)

    # Test 1y range (daily)
    print("\n--- 1y / 1d ---")
    hist_day = ticker.history(period="1y", interval="1d")
    if hist_day.empty:
        print("Empty history")
    else:
        print("Index dtype:", hist_day.index.dtype)
        print("First index val:", hist_day.index[0])
        try:
            timestamps = (hist_day.index.astype('int64') // 10**9).tolist()
            print("First timestamp (sec):", timestamps[0])
            print("First timestamp (date):", pd.to_datetime(timestamps[0], unit='s'))
        except Exception as e:
            print("Conversion failed:", e)

if __name__ == "__main__":
    test_conversion()
