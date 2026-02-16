
"""
Wishlist blueprint – CRUD for stock wishlist.
"""

from flask import Blueprint, request, jsonify
from database import query
import json

wishlist_bp = Blueprint("wishlist", __name__)

@wishlist_bp.route("/api/wishlist", methods=["GET"])
def get_wishlist():
    """Return all wishlist items."""
    items = query(
        "SELECT * FROM wishlist ORDER BY added_at DESC",
        fetchall=True,
    )
    
    # Process items to ensure correct types for JSON
    results = []
    if items:
        for item in items:
            # Create a clean copy
            clean_item = {
                "id": item.get("id"),
                "symbol": item.get("symbol"),
                "added_at": str(item.get("added_at")),
                "initial_price": float(item.get("initial_price")) if item.get("initial_price") is not None else None,
                "note": item.get("note"),
                "snapshot": item.get("snapshot")
            }
            results.append(clean_item)

    return jsonify({"wishlist": results})

@wishlist_bp.route("/api/wishlist", methods=["POST"])
def add_to_wishlist():
    """Add a stock to the wishlist."""
    body = request.get_json(force=True)
    
    symbol = body.get("symbol")
    if not symbol:
        return jsonify({"error": "Symbol is required"}), 400
        
    initial_price = body.get("initial_price")
    note = body.get("note", "")
    snapshot = body.get("snapshot", {})
    
    # Ensure snapshot is JSON serializable string if it's a dict, 
    # but psycopg2 adapter for JSONB handles dicts automatically.
    # We do need to make sure the dict content is JSON compliant though.
    
    try:
        query(
            """
            INSERT INTO wishlist (symbol, initial_price, note, snapshot)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                initial_price = EXCLUDED.initial_price,
                note = EXCLUDED.note,
                snapshot = EXCLUDED.snapshot,
                added_at = NOW()
            """,
            (symbol, initial_price, note, json.dumps(snapshot) if snapshot else '{}')
        )
        return jsonify({"ok": True, "symbol": symbol})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@wishlist_bp.route("/api/wishlist/<symbol>", methods=["DELETE"])
def remove_from_wishlist(symbol):
    """Remove a stock from the wishlist."""
    query("DELETE FROM wishlist WHERE symbol = %s", (symbol,))
    return jsonify({"ok": True, "symbol": symbol})
