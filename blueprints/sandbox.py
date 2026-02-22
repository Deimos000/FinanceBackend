"""
Sandbox blueprint – CRUD for stock sandboxes and trading logic.
"""

from flask import Blueprint, request, jsonify
from database import query
import yfinance as yf
import pandas as pd
import datetime
from blueprints.auth import login_required

sandbox_bp = Blueprint("sandbox", __name__)


def _check_sandbox_access(sandbox_id, user_id, required_permission="watch"):
    """
    Check if a user has access to a sandbox.
    Returns (sandbox_owner_id, permission) or (None, None).
    - Owner always has full access.
    - Shared users checked against required_permission.
    """
    # Check ownership first
    sandbox = query(
        "SELECT id, user_id FROM sandboxes WHERE id = %s", (sandbox_id,), fetchone=True
    )
    if not sandbox:
        return None, None

    if sandbox["user_id"] == user_id:
        return sandbox["user_id"], "owner"

    # Check shared access
    share = query(
        "SELECT permission FROM sandbox_shares WHERE sandbox_id = %s AND shared_with_id = %s",
        (sandbox_id, user_id),
        fetchone=True,
    )
    if not share:
        return None, None

    permission = share["permission"]
    # For 'edit' required, only 'edit' permission works
    if required_permission == "edit" and permission != "edit":
        return None, None

    return sandbox["user_id"], permission

def _get_historical_prices(symbols, start_date):
    """
    Fetch historical close prices for given symbols from start_date to now.
    Returns a DataFrame accessed by [date][symbol].
    """
    if not symbols: return pd.DataFrame()
    
    try:
        # yfinance expects YYYY-MM-DD string
        start_str = start_date.strftime('%Y-%m-%d')
        # Download all at once
        data = yf.download(symbols, start=start_str, progress=False)['Close']
        
        # If single symbol, yfinance returns Series (or DF with 1 col). Ensure DF.
        if isinstance(data, pd.Series):
            data = data.to_frame(name=symbols[0])
            
        # Forward fill missing data (weekend/holidays) then backward fill
        data = data.ffill().bfill()
        
        return data
    except Exception as e:
        print(f"Error fetching historical prices: {e}")
        return pd.DataFrame()

def _calculate_portfolio_history(sandbox_id, initial_balance, transactions, created_at):
    """
    Reconstruct daily portfolio value from transactions.
    """
    try:
        # 1. Timeline Setup
        # Start from creation date or first transaction, whichever is earlier
        start_date = created_at.date()
        if transactions:
            first_tx_date = transactions[0]['executed_at'].date()
            if first_tx_date < start_date:
                start_date = first_tx_date
                
        # Generate date range until today
        end_date = datetime.date.today()
        # Create a date range (pandas DateTimeIndex)
        all_dates = pd.date_range(start_date, end_date)
        
        # 2. Identify all symbols involved
        symbols = set(t['symbol'] for t in transactions)
        
        # 3. Fetch Historical Prices
        price_df = _get_historical_prices(list(symbols), start_date)
        
        # Reindex to ensure we have values for every single day in the range
        # This handles weekends/holidays by carrying forward the last close price
        if not price_df.empty:
            price_df = price_df.reindex(all_dates).ffill().bfill()
        
        # Format timestamps for efficient lookup
        # price_df index is DatetimeIndex. We'll map dates to prices.
        
        # 4. Reconstruct State Day-by-Day
        history = []
        
        current_cash = float(initial_balance)
        current_holdings = {sym: 0.0 for sym in symbols}
        
        # Organize transactions by date for quick access
        tx_by_date = {}
        for t in transactions:
            d = t['executed_at'].date()
            if d not in tx_by_date: tx_by_date[d] = []
            tx_by_date[d].append(t)
            
        for single_date in all_dates:
            date_obj = single_date.date()
            
            # Apply transactions for this day
            if date_obj in tx_by_date:
                for t in tx_by_date[date_obj]:
                    qty = float(t['quantity'])
                    price = float(t['price'])
                    total = qty * price
                    sym = t['symbol']
                    
                    if t['type'] == 'BUY':
                        current_cash -= total
                        current_holdings[sym] += qty
                    elif t['type'] == 'SELL':
                        current_cash += total
                        current_holdings[sym] -= qty
            
            # Calculate Equity
            equity_holdings = 0.0
            
            # Check if we have price data for this date
            # We use 'single_date' (Timestamp) to lookup in DataFrame
            try:
                if not price_df.empty and single_date in price_df.index:
                    prices_today = price_df.loc[single_date]
                    for sym, qty in current_holdings.items():
                        if qty > 0:
                            # Handle potential missing columns or NaN
                            if sym in prices_today:
                                p = float(prices_today[sym])
                                # Fallback if nan
                                if pd.isna(p): p = 0.0
                                equity_holdings += qty * p
                else:
                     # Fallback: if no price data for this specific day (e.g. weekend/holidays if not filled),
                     # use the last known value? yfinance reindex usually handles this if we implement it right.
                     # But if we are iterating strict calendar days and yfinance only gave trading days...
                     # We should reindex price_df to all_dates beforehand to be safe.
                     pass 
            except Exception as e:
                # print(f"Error calculating equity for {date_obj}: {e}")
                pass

            total_equity = current_cash + equity_holdings
            
            # Add to history
            history.append({
                "timestamp": single_date.timestamp() * 1000,
                "value": total_equity
            })
            
        # Re-fill missing values in our history list if any (shouldn't be with this loop)
        return history

    except Exception as e:
        print(f"History calc error: {e}")
        # Fallback to simple line
        now_ts = datetime.datetime.now().timestamp() * 1000
        start_ts = created_at.timestamp() * 1000
        return [
            {"timestamp": start_ts, "value": initial_balance},
            {"timestamp": now_ts, "value": initial_balance} # Should ideally be current equity
        ]

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
@login_required
def get_sandboxes(user_id):
    """Return all sandboxes with total equity (cash + holdings)."""
    try:
        sandboxes = query("SELECT * FROM sandboxes WHERE user_id = %s ORDER BY created_at DESC", (user_id,), fetchall=True)
        results = []
        
        if sandboxes:
            all_portfolio_items = query("SELECT * FROM sandbox_portfolio", fetchall=True)
            
            portfolio_map = {}
            all_symbols = set()
            
            if all_portfolio_items:
                for item in all_portfolio_items:
                    sid = item["sandbox_id"]
                    if sid not in portfolio_map: portfolio_map[sid] = []
                    portfolio_map[sid].append(item)
                    all_symbols.add(item["symbol"])
            
            prices = _get_current_prices(list(all_symbols))
            
            for s in sandboxes:
                sid = s.get("id")
                balance = float(s.get("balance"))
                initial = float(s.get("initial_balance")) if s.get("initial_balance") else 10000.0
                
                holdings_value = 0.0
                if sid in portfolio_map:
                    for item in portfolio_map[sid]:
                        sym = item["symbol"]
                        qty = float(item["quantity"])
                        price = prices.get(sym, float(item["average_buy_price"]))
                        holdings_value += (price * qty)
                
                total_equity = balance + holdings_value
                
                # Count shares for this sandbox
                share_count = 0
                shares_row = query(
                    "SELECT COUNT(*) as cnt FROM sandbox_shares WHERE sandbox_id = %s",
                    (sid,), fetchone=True
                )
                if shares_row:
                    share_count = shares_row["cnt"]
                
                results.append({
                    "id": sid,
                    "name": s.get("name"),
                    "balance": balance,
                    "initial_balance": initial,
                    "total_equity": total_equity,
                    "created_at": str(s.get("created_at")),
                    "share_count": share_count,
                })
                
        return jsonify({"sandboxes": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sandbox_bp.route("/api/sandbox", methods=["POST"])
@login_required
def create_sandbox(user_id):
    """Create a new sandbox."""
    try:
        body = request.get_json(force=True)
        name = body.get("name")
        if not name:
            return jsonify({"error": "Name is required"}), 400
            
        initial_balance = float(body.get("balance", 10000.00))
        
        res = query(
            "INSERT INTO sandboxes (name, user_id, balance, initial_balance) VALUES (%s, %s, %s, %s) RETURNING id",
            (name, user_id, initial_balance, initial_balance),
            fetchone=True 
        )
        new_id = res["id"]
        return jsonify({"ok": True, "id": new_id, "name": name, "balance": initial_balance})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sandbox_bp.route("/api/sandbox/<int:sandbox_id>", methods=["DELETE"])
@login_required
def delete_sandbox(sandbox_id, user_id):
    """Delete a sandbox."""
    try:
        # Check permissions
        s = query("SELECT id FROM sandboxes WHERE id = %s AND user_id = %s", (sandbox_id, user_id), fetchone=True)
        if not s: return jsonify({"error": "Sandbox not found"}), 404
        # Cascade delete (manual since DB might not have cascade setup)
        query("DELETE FROM sandbox_transactions WHERE sandbox_id = %s AND user_id = %s", (sandbox_id, user_id))
        query("DELETE FROM sandbox_portfolio WHERE sandbox_id = %s AND user_id = %s", (sandbox_id, user_id))
        query("DELETE FROM sandboxes WHERE id = %s AND user_id = %s", (sandbox_id, user_id))
        return jsonify({"ok": True, "id": sandbox_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sandbox_bp.route("/api/sandbox/<int:sandbox_id>/portfolio", methods=["GET"])
@login_required
def get_portfolio(sandbox_id, user_id):
    """Get portfolio for a sandbox with current values and equity history.
    Supports shared access (watch or edit permission)."""
    try:
        # Check access (owner or shared)
        owner_id, permission = _check_sandbox_access(sandbox_id, user_id, "watch")
        if not owner_id:
            return jsonify({"error": "Sandbox not found"}), 404

        # Use owner_id for data queries since portfolio/transactions are stored under owner
        portfolio_items = query(
            "SELECT * FROM sandbox_portfolio WHERE sandbox_id = %s AND user_id = %s",
            (sandbox_id, owner_id),
            fetchall=True
        )
        
        sandbox = query("SELECT balance, initial_balance, created_at FROM sandboxes WHERE id = %s AND user_id = %s", (sandbox_id, owner_id), fetchone=True)
        if not sandbox:
            return jsonify({"error": "Sandbox not found"}), 404
            
        cash_balance = float(sandbox["balance"])
        initial_balance = float(sandbox["initial_balance"]) if sandbox["initial_balance"] else cash_balance
        
        results = []
        holdings_value = 0.0
        
        symbols = [item["symbol"] for item in portfolio_items] if portfolio_items else []
        prices = _get_current_prices(symbols)
        
        if portfolio_items:
            for item in portfolio_items:
                symbol = item.get("symbol")
                qty = float(item.get("quantity"))
                avg_price = float(item.get("average_buy_price"))
                
                current_price = prices.get(symbol, avg_price)
                
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

        transactions = query(
            "SELECT * FROM sandbox_transactions WHERE sandbox_id = %s AND user_id = %s ORDER BY executed_at ASC",
            (sandbox_id, owner_id),
            fetchall=True
        )
        
        equity_history = _calculate_portfolio_history(sandbox_id, initial_balance, transactions, sandbox["created_at"])
        
        return jsonify({
            "portfolio": results,
            "cash_balance": cash_balance,
            "initial_balance": initial_balance,
            "total_equity": total_equity,
            "equity_history": equity_history,
            "permission": permission,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sandbox_bp.route("/api/sandbox/<int:sandbox_id>/transactions", methods=["GET"])
@login_required
def get_transactions(sandbox_id, user_id):
    """Get all transactions. Supports shared access."""
    try:
        owner_id, permission = _check_sandbox_access(sandbox_id, user_id, "watch")
        if not owner_id:
            return jsonify({"error": "Sandbox not found"}), 404

        rows = query(
            "SELECT * FROM sandbox_transactions WHERE sandbox_id = %s AND user_id = %s ORDER BY executed_at DESC",
            (sandbox_id, owner_id),
            fetchall=True
        )
        return jsonify({"transactions": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sandbox_bp.route("/api/sandbox/<int:sandbox_id>/trade", methods=["POST"])
@login_required
def trade_stock(sandbox_id, user_id):
    """Execute a buy or sell trade. Requires edit permission for shared sandboxes."""
    try:
        # Check access – need 'edit' permission to trade
        owner_id, permission = _check_sandbox_access(sandbox_id, user_id, "edit")
        if not owner_id:
            return jsonify({"error": "Sandbox not found or insufficient permissions"}), 404

        body = request.get_json(force=True)
        symbol = body.get("symbol")
        trade_type = body.get("type", "").upper()
        quantity = float(body.get("quantity", 0))
        amount = float(body.get("amount", 0))
        
        if not symbol or trade_type not in ["BUY", "SELL"]:
            return jsonify({"error": "Invalid trade parameters"}), 400
            
        price = _get_current_price(symbol)
        if not price:
            return jsonify({"error": "Could not fetch current price"}), 500
            
        if amount > 0 and quantity <= 0:
            quantity = amount / price
            
        if quantity <= 0:
            return jsonify({"error": "Invalid quantity"}), 400
            
        total_cost = price * quantity
        
        # Use owner_id for all data operations
        sandbox = query("SELECT * FROM sandboxes WHERE id = %s AND user_id = %s", (sandbox_id, owner_id), fetchone=True)
        if not sandbox:
            return jsonify({"error": "Sandbox not found"}), 404
            
        current_balance = float(sandbox["balance"])
        
        if trade_type == "BUY":
            return _execute_buy(sandbox_id, symbol, quantity, price, total_cost, current_balance, owner_id)
        elif trade_type == "SELL":
            return _execute_sell(sandbox_id, symbol, quantity, price, total_cost, current_balance, owner_id)
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def _execute_buy(sandbox_id, symbol, quantity, price, total_cost, current_balance, user_id):
    if current_balance < total_cost:
        return jsonify({"error": f"Insufficient funds (${current_balance:.2f} < ${total_cost:.2f})"}), 400
    
    new_balance = current_balance - total_cost
    query("UPDATE sandboxes SET balance = %s WHERE id = %s AND user_id = %s", (new_balance, sandbox_id, user_id))
    
    # Update Portfolio
    existing = query(
        "SELECT quantity, average_buy_price FROM sandbox_portfolio WHERE sandbox_id = %s AND symbol = %s AND user_id = %s",
        (sandbox_id, symbol, user_id),
        fetchone=True
    )
    
    if existing:
        old_qty = float(existing["quantity"])
        old_avg = float(existing["average_buy_price"])
        new_qty = old_qty + quantity
        new_avg = ((old_qty * old_avg) + (quantity * price)) / new_qty
        
        query(
            "UPDATE sandbox_portfolio SET quantity = %s, average_buy_price = %s WHERE sandbox_id = %s AND symbol = %s AND user_id = %s",
            (new_qty, new_avg, sandbox_id, symbol, user_id)
        )
    else:
        query(
            "INSERT INTO sandbox_portfolio (sandbox_id, user_id, symbol, quantity, average_buy_price) VALUES (%s, %s, %s, %s, %s)",
            (sandbox_id, user_id, symbol, quantity, price)
        )
        
    _record_transaction(sandbox_id, symbol, "BUY", quantity, price, user_id)
    
    return jsonify({
        "ok": True, 
        "type": "BUY", 
        "symbol": symbol, 
        "price": price, 
        "quantity": quantity, 
        "total": total_cost,
        "new_balance": new_balance
    })

def _execute_sell(sandbox_id, symbol, quantity, price, total_cost, current_balance, user_id):
    existing = query(
        "SELECT quantity FROM sandbox_portfolio WHERE sandbox_id = %s AND symbol = %s AND user_id = %s",
        (sandbox_id, symbol, user_id),
        fetchone=True
    )
    owned_qty = float(existing["quantity"]) if existing else 0
    
    if owned_qty < quantity:
        return jsonify({"error": f"Insufficient shares ({owned_qty} < {quantity})"}), 400
        
    new_balance = current_balance + total_cost
    query("UPDATE sandboxes SET balance = %s WHERE id = %s AND user_id = %s", (new_balance, sandbox_id, user_id))
    
    new_qty = owned_qty - quantity
    if new_qty <= 0.000001:
        query("DELETE FROM sandbox_portfolio WHERE sandbox_id = %s AND symbol = %s AND user_id = %s", (sandbox_id, symbol, user_id))
    else:
        query(
            "UPDATE sandbox_portfolio SET quantity = %s WHERE sandbox_id = %s AND symbol = %s AND user_id = %s",
            (new_qty, sandbox_id, symbol, user_id)
        )
        
    _record_transaction(sandbox_id, symbol, "SELL", quantity, price, user_id)
    
    return jsonify({
        "ok": True, 
        "type": "SELL", 
        "symbol": symbol, 
        "price": price, 
        "quantity": quantity, 
        "total": total_cost,
        "new_balance": new_balance
    })

def _record_transaction(sandbox_id, symbol, trade_type, quantity, price, user_id):
    query(
        "INSERT INTO sandbox_transactions (sandbox_id, user_id, symbol, type, quantity, price) VALUES (%s, %s, %s, %s, %s, %s)",
        (sandbox_id, user_id, symbol, trade_type, quantity, price)
    )
