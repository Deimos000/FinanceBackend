"""
Cash account blueprint – virtual cash account + transactions.
"""

import uuid
from flask import Blueprint, request, jsonify
from database import query
from blueprints.auth import login_required

cash_bp = Blueprint("cash", __name__)


def _ensure_cash_account(user_id):
    """Create the cash account row if it doesn't exist, return it."""
    cash_account_id = f"CASH_{user_id}"
    acc = query(
        "SELECT * FROM accounts WHERE account_id = %s AND user_id = %s",
        (cash_account_id, user_id),
        fetchone=True,
    )
    if acc:
        return acc

    query(
        """
        INSERT INTO accounts (account_id, user_id, name, iban, balance, currency, bank_name, type, subtype)
        VALUES (%s, %s, 'Cash Account', 'N/A', 0, 'EUR', 'Cash', 'cash', 'cash')
        """,
        (cash_account_id, user_id),
    )
    return query(
        "SELECT * FROM accounts WHERE account_id = %s",
        (cash_account_id,),
        fetchone=True,
    )


@cash_bp.route("/api/cash/account", methods=["GET"])
@login_required
def get_cash_account(user_id):
    acc = _ensure_cash_account(user_id)
    acc["balance"] = float(acc["balance"])

    # Also fetch cash transactions
    txs = query(
        "SELECT * FROM cash_transactions WHERE user_id = %s ORDER BY booking_date DESC",
        (user_id,),
        fetchall=True,
    )
    for t in txs:
        t["amount"] = float(t["amount"])
        t["booking_date"] = str(t["booking_date"])

    acc["transactions"] = txs
    return jsonify(acc)


@cash_bp.route("/api/cash/account", methods=["POST"])
@login_required
def create_cash_account(user_id):
    acc = _ensure_cash_account(user_id)
    acc["balance"] = float(acc["balance"])
    return jsonify(acc)


@cash_bp.route("/api/cash/balance", methods=["PUT"])
@login_required
def update_balance(user_id):
    body = request.get_json(force=True)
    new_balance = body.get("balance", 0)
    cash_account_id = f"CASH_{user_id}"

    query(
        "UPDATE accounts SET balance = %s, last_synced = NOW() WHERE account_id = %s AND user_id = %s",
        (new_balance, cash_account_id, user_id),
    )
    return jsonify({"ok": True, "balance": new_balance})


@cash_bp.route("/api/cash/transaction", methods=["POST"])
@login_required
def add_transaction(user_id):
    body = request.get_json(force=True)
    amount = body.get("amount", 0)
    name = body.get("name", "Cash Deposit" if amount > 0 else "Cash Payment")
    description = body.get("description", "Manual Transaction")
    tx_id = str(uuid.uuid4())
    cash_account_id = f"CASH_{user_id}"

    display_name = f"{name} (cash)"

    query(
        """
        INSERT INTO cash_transactions (id, user_id, amount, currency, name, description)
        VALUES (%s, %s, %s, 'EUR', %s, %s)
        """,
        (tx_id, user_id, amount, display_name, description),
    )

    # Update cash account balance
    query(
        "UPDATE accounts SET balance = balance + %s, last_synced = NOW() WHERE account_id = %s AND user_id = %s",
        (amount, cash_account_id, user_id),
    )

    return jsonify({
        "id": tx_id,
        "amount": amount,
        "name": display_name,
        "description": description,
    })
