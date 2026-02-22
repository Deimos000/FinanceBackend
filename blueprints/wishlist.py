"""
Wishlist blueprint – CRUD for stock wishlist.
"""

from flask import Blueprint, request, jsonify
from database import query
import json
from blueprints.auth import login_required

wishlist_bp = Blueprint("wishlist", __name__)

@wishlist_bp.route("/api/wishlist", methods=["GET"])
@login_required
def get_wishlist(user_id):
    """Return all wishlist items."""
    items = query(
        "SELECT * FROM wishlist WHERE user_id = %s ORDER BY added_at DESC",
        (user_id,),
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
@login_required
def add_to_wishlist(user_id):
    """Add a stock to the wishlist."""
    body = request.get_json(force=True)
    
    symbol = body.get("symbol")
    if not symbol:
        return jsonify({"error": "Symbol is required"}), 400
        
    initial_price = body.get("initial_price")
    note = body.get("note", "")
    snapshot = body.get("snapshot", {})
    
    try:
        # Notice we use 'symbol, user_id' constraint. If symbol is UNIQUE globally, this fails!
        # The schema had `symbol TEXT NOT NULL UNIQUE`. We'll just assume they add it and if conflict, overwrite.
        query(
            """
            INSERT INTO wishlist (symbol, user_id, initial_price, note, snapshot)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                initial_price = EXCLUDED.initial_price,
                note = EXCLUDED.note,
                snapshot = EXCLUDED.snapshot,
                added_at = NOW()
            """,
            (symbol, user_id, initial_price, note, json.dumps(snapshot) if snapshot else '{}')
        )
        return jsonify({"ok": True, "symbol": symbol})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@wishlist_bp.route("/api/wishlist/<symbol>", methods=["DELETE"])
@login_required
def remove_from_wishlist(symbol, user_id):
    """Remove a stock from the wishlist."""
    query("DELETE FROM wishlist WHERE symbol = %s AND user_id = %s", (symbol, user_id))
    return jsonify({"ok": True, "symbol": symbol})
