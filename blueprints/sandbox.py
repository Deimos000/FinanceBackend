"""
Sandbox blueprint – CRUD for stock sandboxes and trading logic.
"""

from flask import Blueprint, request, jsonify
from database import query
import yfinance as yf
import json

sandbox_bp = Blueprint("sandbox", __name__)

def _get_current_price(symbol):
    """Helper to get real-time price from yfinance."""
    try:
        ticker = yf.Ticker(symbol)
        # Try fast_info first, then regular info
        price = ticker.fast_info.last_price
        if price is None:
            price = ticker.info.get("currentPrice") or ticker.info.get("regularMarketPrice")
        return price
    except Exception as e:
        print(f"Error fetching price for {symbol}: {e}")
        return None

@sandbox_bp.route("/api/sandboxes", methods=["GET"])
def get_sandboxes():
    """Return all sandboxes."""
    sandboxes = query(
        "SELECT * FROM sandboxes ORDER BY created_at DESC",
        fetchall=True,
    )
    
    results = []
    if sandboxes:
        for s in sandboxes:
            results.append({
                "id": s.get("id"),
                "name": s.get("name"),
                "balance": float(s.get("balance")),
                "initial_balance": float(s.get("initial_balance")) if s.get("initial_balance") else None,
                "created_at": str(s.get("created_at")),
            })

    return jsonify({"sandboxes": results})

@sandbox_bp.route("/api/sandbox", methods=["POST"])
def create_sandbox():
    """Create a new sandbox."""
    body = request.get_json(force=True)
    name = body.get("name")
    if not name:
        return jsonify({"error": "Name is required"}), 400
        
    initial_balance = body.get("balance", 10000.00)
    
    try:
        # Returning ID is specific to PostgreSQL INSERT ... RETURNING id
        res = query(
            """
            INSERT INTO sandboxes (name, balance, initial_balance)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (name, initial_balance, initial_balance),
            fetchall=True 
        )
        new_id = res[0]["id"]
        return jsonify({"ok": True, "id": new_id, "name": name, "balance": initial_balance})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sandbox_bp.route("/api/sandbox/<int:sandbox_id>", methods=["DELETE"])
def delete_sandbox(sandbox_id):
    """Delete a sandbox."""
    query("DELETE FROM sandboxes WHERE id = %s", (sandbox_id,))
    return jsonify({"ok": True, "id": sandbox_id})

@sandbox_bp.route("/api/sandbox/<int:sandbox_id>/portfolio", methods=["GET"])
def get_portfolio(sandbox_id):
    """Get portfolio for a sandbox with current values."""
    portfolio_items = query(
        "SELECT * FROM sandbox_portfolio WHERE sandbox_id = %s",
        (sandbox_id,),
        fetchall=True
    )
    
    results = []
    total_value = 0.0
    
    if portfolio_items:
        for item in portfolio_items:
            symbol = item.get("symbol")
            qty = float(item.get("quantity"))
            avg_price = float(item.get("average_buy_price"))
            
            # Fetch current price to show performace
            current_price = _get_current_price(symbol)
            current_val = (current_price * qty) if current_price else 0.0
            total_value += current_val
            
            results.append({
                "symbol": symbol,
                "quantity": qty,
                "average_buy_price": avg_price,
                "current_price": current_price,
                "current_value": current_val,
                "gain_loss": (current_price - avg_price) * qty if current_price else 0.0,
                "gain_loss_percent": ((current_price - avg_price) / avg_price * 100) if current_price and avg_price > 0 else 0.0
            })
            
    # Also get cash balance
    sandbox = query("SELECT balance FROM sandboxes WHERE id = %s", (sandbox_id,), fetchall=True)
    cash_balance = float(sandbox[0]["balance"]) if sandbox else 0.0
    
    return jsonify({
        "portfolio": results,
        "cash_balance": cash_balance,
        "total_equity": cash_balance + total_value
    })

@sandbox_bp.route("/api/sandbox/<int:sandbox_id>/trade", methods=["POST"])
def trade_stock(sandbox_id):
    """Execute a buy or sell trade."""
    body = request.get_json(force=True)
    symbol = body.get("symbol")
    trade_type = body.get("type", "").upper() # BUY or SELL
    quantity = float(body.get("quantity", 0))
    
    if not symbol or trade_type not in ["BUY", "SELL"] or quantity <= 0:
        return jsonify({"error": "Invalid trade parameters"}), 400
        
    # 1. Get current price
    price = _get_current_price(symbol)
    if not price:
        return jsonify({"error": "Could not fetch current price"}), 500
        
    total_cost = price * quantity
    
    # 2. Get Sandbox state
    sandbox = query("SELECT balance FROM sandboxes WHERE id = %s", (sandbox_id,), fetchall=True)
    if not sandbox:
        return jsonify({"error": "Sandbox not found"}), 404
        
    current_balance = float(sandbox[0]["balance"])
    
    # 3. Validation & Execution Logic
    if trade_type == "BUY":
        if current_balance < total_cost:
            return jsonify({"error": "Insufficient funds"}), 400
            
        # Deduct Balance
        new_balance = current_balance - total_cost
        query("UPDATE sandboxes SET balance = %s WHERE id = %s", (new_balance, sandbox_id))
        
        # Update Portfolio
        existing = query(
            "SELECT quantity, average_buy_price FROM sandbox_portfolio WHERE sandbox_id = %s AND symbol = %s",
            (sandbox_id, symbol),
            fetchall=True
        )
        
        if existing:
            old_qty = float(existing[0]["quantity"])
            old_avg = float(existing[0]["average_buy_price"])
            new_qty = old_qty + quantity
            # Weighted Average Price
            new_avg = ((old_qty * old_avg) + (quantity * price)) / new_qty
            
            query(
                "UPDATE sandbox_portfolio SET quantity = %s, average_buy_price = %s WHERE sandbox_id = %s AND symbol = %s",
                (new_qty, new_avg, sandbox_id, symbol)
            )
        else:
            query(
                "INSERT INTO sandbox_portfolio (sandbox_id, symbol, quantity, average_buy_price) VALUES (%s, %s, %s, %s)",
                (sandbox_id, symbol, quantity, price)
            )
            
    elif trade_type == "SELL":
        existing = query(
            "SELECT quantity FROM sandbox_portfolio WHERE sandbox_id = %s AND symbol = %s",
            (sandbox_id, symbol),
            fetchall=True
        )
        if not existing:
             return jsonify({"error": "Stock not owned"}), 400
             
        owned_qty = float(existing[0]["quantity"])
        if owned_qty < quantity:
            return jsonify({"error": "Insufficient quantity"}), 400
            
        # Add Balance
        new_balance = current_balance + total_cost
        query("UPDATE sandboxes SET balance = %s WHERE id = %s", (new_balance, sandbox_id))
        
        # Update Portfolio
        new_qty = owned_qty - quantity
        if new_qty <= 0.000001: # Float precision safety
            query("DELETE FROM sandbox_portfolio WHERE sandbox_id = %s AND symbol = %s", (sandbox_id, symbol))
        else:
            query("UPDATE sandbox_portfolio SET quantity = %s WHERE sandbox_id = %s AND symbol = %s", (new_qty, sandbox_id, symbol))
            
    # 4. Record Transaction
    query(
        """
        INSERT INTO sandbox_transactions (sandbox_id, symbol, type, quantity, price)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (sandbox_id, symbol, trade_type, quantity, price)
    )
    
    return jsonify({
        "ok": True, 
        "type": trade_type, 
        "symbol": symbol, 
        "price": price, 
        "quantity": quantity,
        "new_balance": new_balance
    })
