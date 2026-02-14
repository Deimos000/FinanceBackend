import sys
import os
import json
from flask import Flask

# Add current directory to path
sys.path.append(os.getcwd())

from blueprints.stocks import stocks_bp

app = Flask(__name__)
app.register_blueprint(stocks_bp)

def test_quote(symbol="AAPL"):
    print(f"Testing quote for {symbol}...")
    with app.test_request_context(f"/api/yahoo-proxy?symbol={symbol}&range=1d&interval=1d"):
        try:
            # We need to access the view function directly or dispatch request
            # Simpler to just use test client
            client = app.test_client()
            response = client.get(f"/api/yahoo-proxy?symbol={symbol}&range=1d&interval=1d")
            
            if response.status_code != 200:
                print(f"FAILED: Status {response.status_code}")
                print(response.get_json())
                return
            
            data = response.get_json()
            
            # Verify structure
            if "chart" not in data or "result" not in data["chart"]:
                print("FAILED: Invalid structure (missing chart.result)")
                print(json.dumps(data, indent=2)[:200])
                return

            result = data["chart"]["result"][0]
            if "meta" not in result or "timestamp" not in result or "indicators" not in result:
                print("FAILED: Invalid result structure")
                print(json.dumps(result, indent=2)[:200])
                return
                
            print(f"SUCCESS: Fetched data for {symbol}")
            print(f"Price: {result['meta'].get('regularMarketPrice')}")
            print(f"Points: {len(result['timestamp'])}")
            
        except Exception as e:
            print(f"EXCEPTION: {e}")

def test_search(query="Apple"):
    print(f"Testing search for {query}...")
    client = app.test_client()
    response = client.get(f"/api/yahoo-proxy?type=search&query={query}")
    
    if response.status_code != 200:
        print(f"FAILED: Status {response.status_code}")
        print(response.get_json())
        return

    data = response.get_json()
    print(f"SUCCESS: Search returned {len(data.get('quotes', [])) if 'quotes' in data else 'unknown'} results")

if __name__ == "__main__":
    print("--- Verifying Stock Migration ---")
    try:
        import yfinance
        print("yfinance is installed.")
    except ImportError:
        print("WARNING: yfinance is NOT installed. Verification will likely fail.")
    
    test_quote()
    test_search()
