"""
Accounts blueprint – CRUD for bank / cash accounts.
"""

from flask import Blueprint, request, jsonify
from database import query

accounts_bp = Blueprint("accounts", __name__)


@accounts_bp.route("/api/accounts", methods=["GET"])
def get_accounts():
    """Return every account together with its transactions."""
    accounts = query(
        "SELECT * FROM accounts ORDER BY created_at",
        fetchall=True,
    )

    for acc in accounts:
        txs = query(
            """
            SELECT * FROM transactions
            WHERE account_id = %s
            ORDER BY booking_date DESC
            """,
            (acc["account_id"],),
            fetchall=True,
        )

        # Add computed display fields the frontend expects
        for t in txs:
            clean_name = t.get("creditor_name") or t.get("debtor_name")
            if not clean_name and t.get("remittance_information"):
                import re
                m = re.match(r"^(.*?) Sent from", t["remittance_information"], re.I)
                if m:
                    clean_name = m.group(1).strip()

            t["id"] = t["transaction_id"]
            t["date"] = str(t["booking_date"])
            t["amount"] = float(t["amount"])
            t["recipient"] = clean_name or "Unknown"
            t["description"] = (
                t.get("remittance_information")
                or t.get("creditor_name")
                or t.get("debtor_name")
                or ""
            )

        acc["id"] = acc["account_id"]
        acc["balance"] = float(acc["balance"])
        acc["bankName"] = acc.get("bank_name", "Bank")
        acc["transactions"] = txs

    return jsonify({"accounts": accounts})


@accounts_bp.route("/api/accounts", methods=["POST"])
def upsert_account():
    """Create or update an account."""
    body = request.get_json(force=True)

    # Resolve account id
    account_id = body.get("uid") or body.get("account_id") or body.get("iban")
    if not account_id or not isinstance(account_id, str):
        return jsonify({"error": "Missing or invalid account_id"}), 400

    # Parse balance -----------------------------------------------------------
    balance = 0.0
    bal = body.get("balances")
    if isinstance(bal, dict) and "current" in bal:
        balance = float(bal["current"])
    elif isinstance(bal, list) and len(bal) > 0:
        first = bal[0]
        amt = (
            first.get("amount", {}).get("amount")
            or first.get("balanceAmount", {}).get("amount")
            or first.get("balance_amount", {}).get("amount")
        )
        if amt:
            balance = float(amt)

    # Determine bank name heuristic
    iban = body.get("iban", "")
    bank_name = body.get("bank_name") or "Bank"
    if "541001100" in iban:
        bank_name = "N26"
    elif "72160400" in iban:
        bank_name = "Commerzbank"

    # Upsert via ON CONFLICT
    query(
        """
        INSERT INTO accounts (account_id, name, iban, balance, currency, bank_name, type, subtype, last_synced)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (account_id) DO UPDATE SET
            name       = EXCLUDED.name,
            iban       = EXCLUDED.iban,
            balance    = CASE
                            WHEN EXCLUDED.balance = 0 AND accounts.balance != 0
                                THEN accounts.balance
                            ELSE EXCLUDED.balance
                         END,
            currency   = EXCLUDED.currency,
            bank_name  = EXCLUDED.bank_name,
            last_synced = NOW()
        """,
        (
            account_id,
            body.get("name", "Bank Account"),
            iban,
            balance,
            body.get("currency", "EUR"),
            bank_name,
            body.get("type", "depository"),
            body.get("subtype", "checking"),
        ),
    )

    return jsonify({"ok": True, "account_id": account_id})


@accounts_bp.route("/api/accounts/<account_id>", methods=["DELETE"])
def delete_account(account_id):
    """Delete an account and all its transactions (CASCADE)."""
    deleted = query("DELETE FROM accounts WHERE account_id = %s", (account_id,))
    if deleted == 0:
        return jsonify({"error": "Account not found"}), 404
    return jsonify({"ok": True})
