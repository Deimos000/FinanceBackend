"""
Transactions blueprint – save & query transactions, analytics aggregations.
"""

import hashlib, base64, json, re
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from database import query

transactions_bp = Blueprint("transactions", __name__)


# ── helpers ────────────────────────────────────────────────

def _stable_id(t, account_id):
    """Derive a deterministic transaction id."""
    tid = t.get("transaction_id") or t.get("transactionId") or t.get("entry_reference")
    if tid:
        return str(tid)
    raw = f"{account_id}-{t.get('booking_date','')}-{t.get('amount',0)}"
    return base64.b64encode(raw.encode()).decode()


def save_transaction(t, account_id):
    """Upsert one raw transaction dict into the database."""
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

    stable_id = _stable_id(t, account_id)

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
            stable_id,
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


# ── routes ─────────────────────────────────────────────────

@transactions_bp.route("/api/transactions", methods=["GET"])
def get_transactions():
    """List transactions with optional filters: account_id, days."""
    account_id = request.args.get("account_id")
    days = request.args.get("days", type=int)

    clauses = []
    params = []

    if account_id:
        clauses.append("account_id = %s")
        params.append(account_id)
    if days:
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        clauses.append("booking_date >= %s")
        params.append(cutoff)

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
    """Sum of absolute spending per day (negative amounts) for the last N days."""
    days = request.args.get("days", 30, type=int)
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    rows = query(
        """
        SELECT booking_date::text AS date, SUM(ABS(amount)) AS amount
        FROM transactions
        WHERE amount < 0 AND booking_date >= %s
        GROUP BY booking_date
        ORDER BY booking_date
        """,
        (cutoff,),
        fetchall=True,
    )

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
