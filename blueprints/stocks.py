"""
Yahoo Finance proxy blueprint.
"""

import random
import requests as http_requests
from flask import Blueprint, request, jsonify

stocks_bp = Blueprint("stocks", __name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]


@stocks_bp.route("/api/yahoo-proxy", methods=["GET"])
def yahoo_proxy():
    qtype = request.args.get("type", "quote")
    query_str = request.args.get("query")
    symbol = request.args.get("symbol")

    if qtype == "search":
        if not query_str:
            return jsonify({"error": "Query param required for search"}), 400
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={query_str}&quotesCount=10&newsCount=0"
    else:
        if not symbol:
            return jsonify({"error": "Symbol param required for quote"}), 400
        interval = request.args.get("interval", "1d")
        rng = request.args.get("range", "1y")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={rng}"

    try:
        resp = http_requests.get(
            url,
            headers={"User-Agent": random.choice(_USER_AGENTS)},
            timeout=15,
        )

        if not resp.ok:
            if resp.status_code == 429:
                return jsonify({"error": "Rate limit exceeded. Please try again later.", "details": resp.text}), 429
            return jsonify({"error": f"Yahoo API Error: {resp.reason}", "details": resp.text}), resp.status_code

        return jsonify(resp.json())

    except Exception as e:
        return jsonify({"error": "Failed to fetch stock data", "details": str(e)}), 500
