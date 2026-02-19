"""
Transactions blueprint – save & query transactions, analytics aggregations.
"""

import hashlib, base64, json, re
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from database import query

transactions_bp = Blueprint("transactions", __name__)


# ── helpers ────────────────────────────────────────────────

def _legacy_stable_id(t, account_id):
    """Derive a deterministic transaction id (LEGACY method)."""
    tid = t.get("transaction_id") or t.get("transactionId") or t.get("entry_reference")
    if tid:
        return str(tid)
    raw = f"{account_id}-{t.get('booking_date','')}-{t.get('amount',0)}"
    return base64.b64encode(raw.encode()).decode()


def _robust_stable_id(t, account_id):
    """
    Derive a robust deterministic transaction id using SHA256.
    Includes more fields to prevent collisions on same-day, same-amount transactions.
    """
    # 1. Prefer explicit bank ID if available
    tid = t.get("transaction_id") or t.get("transactionId") or t.get("entry_reference")
    if tid:
        return str(tid)

    # 2. Construct unique string from fields
    # We include: account_id, date, amount, currency, recipient, sender, remittance
    
    amount = t.get("amount")
    # Handle amount dict or value
    if isinstance(amount, dict):
        amt_val = amount.get("amount", 0)
        curr = amount.get("currency", "EUR")
    else:
        amt_val = amount
        curr = t.get("currency", "EUR")
        
    booking_date = t.get("booking_date") or t.get("date") or ""
    
    creditor = t.get("creditor_name") or (t.get("creditor") or {}).get("name") or ""
    debtor   = t.get("debtor_name") or (t.get("debtor") or {}).get("name") or ""
    
    remittance = t.get("remittance_information") or t.get("remittance_information_unstructured") or ""
    if isinstance(remittance, list):
        remittance = " ".join(remittance)

    raw = f"{account_id}|{booking_date}|{amt_val}|{curr}|{creditor}|{debtor}|{remittance}"
    
    # Return SHA256 hash
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def save_transaction(t, account_id):
    """
    Upsert one raw transaction dict into the database.
    Returns True if a NEW transaction was inserted, False if updated/existing.
    """
    amount = 0.0
    ta = t.get("transaction_amount") or {}
    if ta.get("amount"):
        amount = float(ta["amount"])
    elif isinstance(t.get("amount"), (int, float)):
        amount = float(t["amount"])

    indicator = t.get("credit_debit_indicator", "")
    if indicator in ("DBIT", "D"):
        amount = -abs(amount)
    elif indicator in ("CRDT", "C"):
        amount = abs(amount)

    # Calculate IDs
    new_id = _robust_stable_id(t, account_id)
    old_id = _legacy_stable_id(t, account_id)

    creditor = t.get("creditor_name") or (t.get("creditor") or {}).get("name")
    debtor   = t.get("debtor_name") or (t.get("debtor") or {}).get("name")

    remittance = t.get("remittance_information") or t.get("remittance_information_unstructured") or ""
    if isinstance(remittance, list):
        remittance = " ".join(remittance)

    # Try extracting names from remittance
    if not creditor and not debtor and remittance:
        m = re.match(r"^(.*?) Sent from", remittance, re.I)
        if m:
            creditor = m.group(1).strip()

    booking = t.get("value_date") or t.get("booking_date") or t.get("bookingDate")
    currency = ta.get("currency") or t.get("currency") or "EUR"

    # 1. Check if we need to migrate an old ID
    # If old_id exists in DB but new_id does not, we update the ID.
    existing_old = query("SELECT 1 FROM transactions WHERE transaction_id = %s", (old_id,), one=True)
    existing_new = query("SELECT 1 FROM transactions WHERE transaction_id = %s", (new_id,), one=True)
    
    if existing_old and not existing_new:
        # MIGRATE
        query("UPDATE transactions SET transaction_id = %s WHERE transaction_id = %s", (new_id, old_id))
        # After migration, it counts as "existing" since we just updated the ID
        existing_new = True 

    # 2. Upsert
    query(
        """
        INSERT INTO transactions
            (transaction_id, account_id, booking_date, amount, currency,
             creditor_name, debtor_name, remittance_information, raw_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (transaction_id) DO UPDATE SET
            amount                 = EXCLUDED.amount,
            currency               = EXCLUDED.currency,
            creditor_name          = EXCLUDED.creditor_name,
            debtor_name            = EXCLUDED.debtor_name,
            remittance_information = EXCLUDED.remittance_information,
            raw_json               = EXCLUDED.raw_json
        """,
        (
            new_id,
            account_id,
            booking,
            amount,
            currency,
            creditor,
            debtor,
            remittance,
            json.dumps(t),
        ),
    )
    
    # Return True if it was NOT existing before (meaning we inserted a new one)
    return not existing_new


# ── routes ─────────────────────────────────────────────────

@transactions_bp.route("/api/transactions", methods=["GET"])
def get_transactions():
    """List transactions with optional filters: account_id, days."""
    account_id = request.args.get("account_id")
    days = request.args.get("days", type=int)
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    clauses = []
    params = []

    if account_id:
        clauses.append("account_id = %s")
        params.append(account_id)
    
    if start_date:
        clauses.append("booking_date >= %s")
        params.append(start_date)
        if end_date:
            clauses.append("booking_date <= %s")
            params.append(end_date)
    elif days:
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        clauses.append("booking_date >= %s")
        params.append(cutoff)

    # Filter for uncategorized
    if request.args.get("uncategorized") == "true":
        clauses.append("(category IS NULL OR category = '')")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = query(
        f"SELECT * FROM transactions {where} ORDER BY booking_date DESC",
        params or None,
        fetchall=True,
    )

    for r in rows:
        r["amount"] = float(r["amount"])
        r["date"] = str(r["booking_date"])
        r["id"] = r["transaction_id"]

    return jsonify({"transactions": rows})


@transactions_bp.route("/api/transactions/daily-spending", methods=["GET"])
def daily_spending():
    """Sum of absolute spending per day (negative amounts) for the last N days OR specific range."""
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    days = request.args.get("days", type=int)

    if not start_date:
        # Fallback to days if no start_date
        d = days if days else 30
        start_date = (datetime.utcnow() - timedelta(days=d)).strftime("%Y-%m-%d")
    
    # Construct query
    sql = """
        SELECT booking_date::text AS date, SUM(ABS(amount)) AS amount
        FROM transactions
        WHERE amount < 0 AND booking_date >= %s
    """
    params = [start_date]

    if end_date:
        sql += " AND booking_date <= %s"
        params.append(end_date)
    
    sql += " GROUP BY booking_date ORDER BY booking_date"

    rows = query(sql, tuple(params), fetchall=True)

    for r in rows:
        r["amount"] = float(r["amount"])

    return jsonify(rows)


@transactions_bp.route("/api/transactions/monthly-income", methods=["GET"])
def monthly_income():
    """Sum of income per month (positive amounts) for the last N months."""
    months = request.args.get("months", 6, type=int)
    cutoff = (datetime.utcnow() - timedelta(days=months * 30)).strftime("%Y-%m-%d")

    rows = query(
        """
        SELECT TO_CHAR(booking_date, 'YYYY-MM') AS month, SUM(amount) AS amount
        FROM transactions
        WHERE amount > 0 AND booking_date >= %s
        GROUP BY TO_CHAR(booking_date, 'YYYY-MM')
        ORDER BY month
        """,
        (cutoff,),
        fetchall=True,
    )

    for r in rows:
        r["amount"] = float(r["amount"])

    return jsonify(rows)

@transactions_bp.route("/api/transactions/<transaction_id>", methods=["PATCH"])
def update_transaction(transaction_id):
    """Update a transaction's category (or other fields in future)."""
    data = request.get_json()
    category = data.get("category")

    if category is not None:
        query(
            "UPDATE transactions SET category = %s WHERE transaction_id = %s",
            (category, transaction_id)
        )
        return jsonify({"status": "updated", "category": category})

    return jsonify({"error": "No valid fields to update"}), 400
