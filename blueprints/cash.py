"""
Cash account blueprint – virtual cash account + transactions.
"""

import uuid
from flask import Blueprint, request, jsonify
from database import query

cash_bp = Blueprint("cash", __name__)

CASH_ACCOUNT_ID = "CASH_ACCOUNT"


def _ensure_cash_account():
    """Create the cash account row if it doesn't exist, return it."""
    acc = query(
        "SELECT * FROM accounts WHERE account_id = %s",
        (CASH_ACCOUNT_ID,),
        fetchone=True,
    )
    if acc:
        return acc

    query(
        """
        INSERT INTO accounts (account_id, name, iban, balance, currency, bank_name, type, subtype)
        VALUES (%s, 'Cash Account', 'N/A', 0, 'EUR', 'Cash', 'cash', 'cash')
        """,
        (CASH_ACCOUNT_ID,),
    )
    return query(
        "SELECT * FROM accounts WHERE account_id = %s",
        (CASH_ACCOUNT_ID,),
        fetchone=True,
    )


@cash_bp.route("/api/cash/account", methods=["GET"])
def get_cash_account():
    acc = _ensure_cash_account()
    acc["balance"] = float(acc["balance"])

    # Also fetch cash transactions
    txs = query(
        "SELECT * FROM cash_transactions ORDER BY booking_date DESC",
        fetchall=True,
    )
    for t in txs:
        t["amount"] = float(t["amount"])
        t["booking_date"] = str(t["booking_date"])

    acc["transactions"] = txs
    return jsonify(acc)


@cash_bp.route("/api/cash/account", methods=["POST"])
def create_cash_account():
    acc = _ensure_cash_account()
    acc["balance"] = float(acc["balance"])
    return jsonify(acc)


@cash_bp.route("/api/cash/balance", methods=["PUT"])
def update_balance():
    body = request.get_json(force=True)
    new_balance = body.get("balance", 0)

    query(
        "UPDATE accounts SET balance = %s, last_synced = NOW() WHERE account_id = %s",
        (new_balance, CASH_ACCOUNT_ID),
    )
    return jsonify({"ok": True, "balance": new_balance})


@cash_bp.route("/api/cash/transaction", methods=["POST"])
def add_transaction():
    body = request.get_json(force=True)
    amount = body.get("amount", 0)
    name = body.get("name", "Cash Deposit" if amount > 0 else "Cash Payment")
    description = body.get("description", "Manual Transaction")
    tx_id = str(uuid.uuid4())

    display_name = f"{name} (cash)"

    query(
        """
        INSERT INTO cash_transactions (id, amount, currency, name, description)
        VALUES (%s, %s, 'EUR', %s, %s)
        """,
        (tx_id, amount, display_name, description),
    )

    # Update cash account balance
    query(
        "UPDATE accounts SET balance = balance + %s, last_synced = NOW() WHERE account_id = %s",
        (amount, CASH_ACCOUNT_ID),
    )

    return jsonify({
        "id": tx_id,
        "amount": amount,
        "name": display_name,
        "description": description,
    })
