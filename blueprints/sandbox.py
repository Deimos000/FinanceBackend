"""
Sandbox blueprint – CRUD for stock sandboxes and trading logic.
"""

from flask import Blueprint, request, jsonify
from database import query
import yfinance as yf
import datetime


sandbox_bp = Blueprint("sandbox", __name__)

def _get_current_price(symbol):
    """Helper to get real-time price from yfinance."""
    try:
        ticker = yf.Ticker(symbol)
        # Try fast_info first (faster)
        price = ticker.fast_info.last_price
        if price: return price
        # Fallback to info
        info = ticker.info
        return info.get("currentPrice") or info.get("regularMarketPrice")
    except Exception as e:
        print(f"Error fetching price for {symbol}: {e}")
        return None

def _get_current_prices(symbols):
    """Helper to get current prices for multiple stocks efficiently."""
    if not symbols: return {}
    try:
        tickers = yf.Tickers(" ".join(symbols))
        prices = {}
        for sym in symbols:
             try:
                 t = tickers.tickers[sym]
                 p = t.fast_info.last_price
                 if p: prices[sym] = p
             except:
                 prices[sym] = 0.0
        return prices
    except:
        return {}

@sandbox_bp.route("/api/sandboxes", methods=["GET"])
def get_sandboxes():
    """Return all sandboxes with total equity (cash + holdings)."""
    try:
        sandboxes = query("SELECT * FROM sandboxes ORDER BY created_at DESC", fetchall=True)
        results = []
        
        if sandboxes:
            # 1. Fetch all portfolio items for all sandboxes to minimize queries
            # Ideally we'd do a JOIN, but for simplicity we can fetch all and map in python
            # or fetching per sandbox (N+1) might be slow if many sandboxes.
            # Let's fetch all portfolio items in one go.
            all_portfolio_items = query("SELECT * FROM sandbox_portfolio", fetchall=True)
            
            # Map items to sandbox_id
            portfolio_map = {} # sandbox_id -> [items]
            all_symbols = set()
            
            if all_portfolio_items:
                for item in all_portfolio_items:
                    sid = item["sandbox_id"]
                    if sid not in portfolio_map: portfolio_map[sid] = []
                    portfolio_map[sid].append(item)
                    all_symbols.add(item["symbol"])
            
            # 2. Get current prices for all symbols
            prices = _get_current_prices(list(all_symbols))
            
            for s in sandboxes:
                sid = s.get("id")
                balance = float(s.get("balance"))
                initial = float(s.get("initial_balance")) if s.get("initial_balance") else 10000.0
                
                # Calculate holdings value
                holdings_value = 0.0
                if sid in portfolio_map:
                    for item in portfolio_map[sid]:
                        sym = item["symbol"]
                        qty = float(item["quantity"])
                        # Use current price or fallback to average buy price if lookup failed
                        price = prices.get(sym, float(item["average_buy_price"]))
                        holdings_value += (price * qty)
                
                total_equity = balance + holdings_value
                
                results.append({
                    "id": sid,
                    "name": s.get("name"),
                    "balance": balance,
                    "initial_balance": initial,
                    "total_equity": total_equity, # Add this field!
                    "created_at": str(s.get("created_at")),
                })
                
        return jsonify({"sandboxes": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sandbox_bp.route("/api/sandbox", methods=["POST"])
def create_sandbox():
    """Create a new sandbox."""
    try:
        body = request.get_json(force=True)
        name = body.get("name")
        if not name:
            return jsonify({"error": "Name is required"}), 400
            
        initial_balance = float(body.get("balance", 10000.00))
        
        res = query(
            "INSERT INTO sandboxes (name, balance, initial_balance) VALUES (%s, %s, %s) RETURNING id",
            (name, initial_balance, initial_balance),
            fetchone=True 
        )
        new_id = res["id"]
        return jsonify({"ok": True, "id": new_id, "name": name, "balance": initial_balance})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sandbox_bp.route("/api/sandbox/<int:sandbox_id>", methods=["DELETE"])
def delete_sandbox(sandbox_id):
    """Delete a sandbox."""
    try:
        # Cascade delete (manual since DB might not have cascade setup)
        query("DELETE FROM sandbox_transactions WHERE sandbox_id = %s", (sandbox_id,))
        query("DELETE FROM sandbox_portfolio WHERE sandbox_id = %s", (sandbox_id,))
        query("DELETE FROM sandboxes WHERE id = %s", (sandbox_id,))
        return jsonify({"ok": True, "id": sandbox_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sandbox_bp.route("/api/sandbox/<int:sandbox_id>/portfolio", methods=["GET"])
def get_portfolio(sandbox_id):
    """Get portfolio for a sandbox with current values and equity history."""
    try:
        # 1. Get Holdings
        portfolio_items = query(
            "SELECT * FROM sandbox_portfolio WHERE sandbox_id = %s",
            (sandbox_id,),
            fetchall=True
        )
        
        # 2. Get Cash Balance
        sandbox = query("SELECT balance, initial_balance, created_at FROM sandboxes WHERE id = %s", (sandbox_id,), fetchone=True)
        if not sandbox:
            return jsonify({"error": "Sandbox not found"}), 404
            
        cash_balance = float(sandbox["balance"])
        initial_balance = float(sandbox["initial_balance"]) if sandbox["initial_balance"] else cash_balance
        
        # 3. Calculate Current Value
        results = []
        holdings_value = 0.0
        
        # Optimize price fetching
        symbols = [item["symbol"] for item in portfolio_items] if portfolio_items else []
        prices = _get_current_prices(symbols)
        
        if portfolio_items:
            for item in portfolio_items:
                symbol = item.get("symbol")
                qty = float(item.get("quantity"))
                avg_price = float(item.get("average_buy_price"))
                
                current_price = prices.get(symbol, avg_price) # Fallback to cost
                
                current_val = (current_price * qty)
                holdings_value += current_val
                
                results.append({
                    "symbol": symbol,
                    "quantity": qty,
                    "average_buy_price": avg_price,
                    "current_price": current_price,
                    "current_value": current_val,
                    "gain_loss": (current_price - avg_price) * qty,
                    "gain_loss_percent": ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0.0
                })

        total_equity = cash_balance + holdings_value

        # 4. Generate Equity History (Simplified)
        # Without historical portfolio snapshots, we interpolate from Initial -> Current
        # Or use transactions to build a 'step' chart of cash + approximate value.
        # For now, we will provide a simple 2-point history to enable the chart.
        # Start: Created At, Value: Initial Balance
        # End: Now, Value: Total Equity
        
        start_ts = sandbox["created_at"].timestamp() * 1000
        now_ts = datetime.datetime.now().timestamp() * 1000
        
        equity_history = [
            {"timestamp": start_ts, "value": initial_balance},
            {"timestamp": now_ts, "value": total_equity}
        ]
        
        # Improve history if we have transactions?
        # TODO: Implement full historical reconstruction later if needed.

        return jsonify({
            "portfolio": results,
            "cash_balance": cash_balance,
            "initial_balance": initial_balance,
            "total_equity": total_equity,
            "equity_history": equity_history
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sandbox_bp.route("/api/sandbox/<int:sandbox_id>/transactions", methods=["GET"])
def get_transactions(sandbox_id):
    """Get all transactions."""
    try:
        rows = query(
            "SELECT * FROM sandbox_transactions WHERE sandbox_id = %s ORDER BY executed_at DESC",
            (sandbox_id,),
            fetchall=True
        )
        return jsonify({"transactions": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sandbox_bp.route("/api/sandbox/<int:sandbox_id>/trade", methods=["POST"])
def trade_stock(sandbox_id):
    """Execute a buy or sell trade."""
    try:
        body = request.get_json(force=True)
        symbol = body.get("symbol")
        trade_type = body.get("type", "").upper() # BUY or SELL
        quantity = float(body.get("quantity", 0))
        amount = float(body.get("amount", 0)) # Support for dollar trades
        
        if not symbol or trade_type not in ["BUY", "SELL"]:
            return jsonify({"error": "Invalid trade parameters"}), 400
            
        # 1. Get current price
        price = _get_current_price(symbol)
        if not price:
            return jsonify({"error": "Could not fetch current price"}), 500
            
        # Determine quantity from amount if needed
        if amount > 0 and quantity <= 0:
            quantity = amount / price
            
        if quantity <= 0:
            return jsonify({"error": "Invalid quantity"}), 400
            
        total_cost = price * quantity
        
        # 2. Get Sandbox state
        sandbox = query("SELECT * FROM sandboxes WHERE id = %s", (sandbox_id,), fetchone=True)
        if not sandbox:
            return jsonify({"error": "Sandbox not found"}), 404
            
        current_balance = float(sandbox["balance"])
        
        # 3. Validation & Execution Logic
        if trade_type == "BUY":
            return _execute_buy(sandbox_id, symbol, quantity, price, total_cost, current_balance)
        elif trade_type == "SELL":
            return _execute_sell(sandbox_id, symbol, quantity, price, total_cost, current_balance)
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def _execute_buy(sandbox_id, symbol, quantity, price, total_cost, current_balance):
    if current_balance < total_cost:
        return jsonify({"error": f"Insufficient funds (${current_balance:.2f} < ${total_cost:.2f})"}), 400
    
    new_balance = current_balance - total_cost
    query("UPDATE sandboxes SET balance = %s WHERE id = %s", (new_balance, sandbox_id))
    
    # Update Portfolio
    existing = query(
        "SELECT quantity, average_buy_price FROM sandbox_portfolio WHERE sandbox_id = %s AND symbol = %s",
        (sandbox_id, symbol),
        fetchone=True
    )
    
    if existing:
        old_qty = float(existing["quantity"])
        old_avg = float(existing["average_buy_price"])
        new_qty = old_qty + quantity
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
        
    _record_transaction(sandbox_id, symbol, "BUY", quantity, price)
    
    return jsonify({
        "ok": True, 
        "type": "BUY", 
        "symbol": symbol, 
        "price": price, 
        "quantity": quantity, 
        "total": total_cost,
        "new_balance": new_balance
    })

def _execute_sell(sandbox_id, symbol, quantity, price, total_cost, current_balance):
    existing = query(
        "SELECT quantity FROM sandbox_portfolio WHERE sandbox_id = %s AND symbol = %s",
        (sandbox_id, symbol),
        fetchone=True
    )
    owned_qty = float(existing["quantity"]) if existing else 0
    
    if owned_qty < quantity:
        return jsonify({"error": f"Insufficient shares ({owned_qty} < {quantity})"}), 400
        
    new_balance = current_balance + total_cost
    query("UPDATE sandboxes SET balance = %s WHERE id = %s", (new_balance, sandbox_id))
    
    new_qty = owned_qty - quantity
    if new_qty <= 0.000001:
        query("DELETE FROM sandbox_portfolio WHERE sandbox_id = %s AND symbol = %s", (sandbox_id, symbol))
    else:
        query(
            "UPDATE sandbox_portfolio SET quantity = %s WHERE sandbox_id = %s AND symbol = %s",
            (new_qty, sandbox_id, symbol)
        )
        
    _record_transaction(sandbox_id, symbol, "SELL", quantity, price)
    
    return jsonify({
        "ok": True, 
        "type": "SELL", 
        "symbol": symbol, 
        "price": price, 
        "quantity": quantity, 
        "total": total_cost,
        "new_balance": new_balance
    })

def _record_transaction(sandbox_id, symbol, trade_type, quantity, price):
    query(
        "INSERT INTO sandbox_transactions (sandbox_id, symbol, type, quantity, price) VALUES (%s, %s, %s, %s, %s)",
        (sandbox_id, symbol, trade_type, quantity, price)
    )
