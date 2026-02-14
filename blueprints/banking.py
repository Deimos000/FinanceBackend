"""
Enable Banking integration blueprint.

Endpoints:
  POST /api/banking/auth-url   – get an auth redirect URL
  POST /api/banking/session    – exchange auth code for accounts + data
  POST /api/banking/refresh    – refresh account balances & transactions
"""

import json, time, requests
import jwt as pyjwt
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from flask import Blueprint, request, jsonify

from config import (
    ENABLE_BANKING_APP_ID,
    ENABLE_BANKING_PRIVATE_KEY,
    ENABLE_BANKING_REDIRECT_URL,
)
from blueprints.transactions import save_transaction
from database import query

banking_bp = Blueprint("banking", __name__)

API_BASE = "https://api.enablebanking.com"


def _create_jwt():
    """Create a signed JWT for Enable Banking API authentication."""
    private_key = load_pem_private_key(
        ENABLE_BANKING_PRIVATE_KEY.encode(), password=None
    )
    now = int(time.time())
    payload = {
        "iss": ENABLE_BANKING_APP_ID,
        "aud": "api.enablebanking.com",
        "iat": now,
        "exp": now + 3600,
    }
    return pyjwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": ENABLE_BANKING_APP_ID},
    )


def _api_headers():
    token = _create_jwt()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _save_account_to_db(acc):
    """Persist an account dict into the accounts table (upsert)."""
    account_id = acc.get("uid") or acc.get("account_id") or acc.get("iban")
    if not account_id or not isinstance(account_id, str):
        return

    # Parse balance
    balance = 0.0
    bal = acc.get("balances")
    if isinstance(bal, dict) and "current" in bal:
        balance = float(bal["current"])
    elif isinstance(bal, list) and len(bal) > 0:
        first = bal[0]
        amt_obj = first.get("amount") or first.get("balanceAmount") or first.get("balance_amount") or {}
        if isinstance(amt_obj, dict) and amt_obj.get("amount"):
            balance = float(amt_obj["amount"])

    iban = acc.get("iban", "")
    bank_name = acc.get("bank_name") or "Bank"
    if "541001100" in iban:
        bank_name = "N26"
    elif "72160400" in iban:
        bank_name = "Commerzbank"

    query(
        """
        INSERT INTO accounts (account_id, name, iban, balance, currency, bank_name, type, subtype, last_synced)
        VALUES (%s, %s, %s, %s, %s, %s, 'depository', 'checking', NOW())
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
            acc.get("name", "Bank Account"),
            iban,
            balance,
            acc.get("currency", "EUR"),
            bank_name,
        ),
    )


# ── auth-url ──────────────────────────────────────────────

@banking_bp.route("/api/banking/auth-url", methods=["POST"])
def auth_url():
    body = request.get_json(force=True) or {}
    bank_name = body.get("bankName", "Commerzbank")

    headers = _api_headers()
    valid_until = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 86400 * 90)
    )

    resp = requests.post(
        f"{API_BASE}/auth",
        headers=headers,
        json={
            "access": {"valid_until": valid_until},
            "aspsp": {"name": bank_name, "country": "DE"},
            "state": "my-personal-request",
            "redirect_url": ENABLE_BANKING_REDIRECT_URL,
        },
    )

    if not resp.ok:
        return jsonify({"error": f"Enable Banking API returned {resp.status_code}", "details": resp.text}), resp.status_code

    data = resp.json()
    if not data.get("url"):
        return jsonify({"error": "No login URL returned", "details": data}), 500

    return jsonify({"url": data["url"]})


# ── session ───────────────────────────────────────────────

@banking_bp.route("/api/banking/session", methods=["POST"])
def session():
    body = request.get_json(force=True)
    code = body.get("code")
    if not code:
        return jsonify({"error": "Missing code"}), 400

    headers = _api_headers()

    resp = requests.post(f"{API_BASE}/sessions", headers=headers, json={"code": code})
    if not resp.ok:
        return jsonify({"error": resp.text}), resp.status_code

    session_data = resp.json()
    accounts = session_data.get("accounts", [])

    for acc in accounts:
        uid = acc.get("uid") or acc.get("account_id") or acc.get("iban")
        if not uid or not isinstance(uid, str):
            continue

        try:
            bal_resp, tx_resp = (
                requests.get(f"{API_BASE}/accounts/{uid}/balances", headers=headers),
                requests.get(
                    f"{API_BASE}/accounts/{uid}/transactions?date_from="
                    + time.strftime("%Y-%m-%d", time.gmtime(time.time() - 90 * 86400)),
                    headers=headers,
                ),
            )

            if bal_resp.ok:
                bal_data = bal_resp.json()
                acc["balances"] = bal_data.get("balances", [])

                # Parse into current balance for our DB
                if acc["balances"] and isinstance(acc["balances"], list):
                    first = acc["balances"][0]
                    amt_obj = first.get("amount") or first.get("balanceAmount") or first.get("balance_amount") or {}
                    if isinstance(amt_obj, dict) and amt_obj.get("amount"):
                        acc.setdefault("_parsed", {})["current"] = float(amt_obj["amount"])

            if tx_resp.ok:
                tx_data = tx_resp.json()
                acc["transactions"] = tx_data.get("transactions", [])
                for t in acc["transactions"]:
                    save_transaction(t, uid)

            _save_account_to_db(acc)

        except Exception as e:
            print(f"[banking/session] Error for {uid}: {e}")

    return jsonify({"accounts": accounts})


# ── refresh ───────────────────────────────────────────────

@banking_bp.route("/api/banking/refresh", methods=["POST"])
def refresh():
    body = request.get_json(force=True)
    accounts = body.get("accounts", [])

    if not isinstance(accounts, list):
        return jsonify({"error": "Missing accounts list"}), 400

    headers = _api_headers()

    updated = []
    for acc in accounts:
        uid = acc.get("raw", {}).get("uid") or acc.get("account_id") or acc.get("uid")
        if not uid or not isinstance(uid, str):
            updated.append(acc)
            continue

        try:
            bal_resp = requests.get(f"{API_BASE}/accounts/{uid}/balances", headers=headers)
            tx_resp = requests.get(
                f"{API_BASE}/accounts/{uid}/transactions?date_from="
                + time.strftime("%Y-%m-%d", time.gmtime(time.time() - 90 * 86400)),
                headers=headers,
            )

            if bal_resp.ok:
                bal_data = bal_resp.json()
                balances = bal_data.get("balances", [])
                if balances:
                    first = balances[0]
                    amt_obj = first.get("amount") or first.get("balanceAmount") or first.get("balance_amount") or {}
                    if isinstance(amt_obj, dict) and amt_obj.get("amount"):
                        parsed_bal = float(amt_obj["amount"])
                        if isinstance(acc.get("balances"), dict):
                            acc["balances"]["current"] = parsed_bal
                        else:
                            acc["balances"] = {"current": parsed_bal, "iso_currency_code": "EUR"}

            if tx_resp.ok:
                tx_data = tx_resp.json()
                acc["transactions"] = tx_data.get("transactions", [])
                for t in acc["transactions"]:
                    save_transaction(t, acc.get("account_id") or uid)
            else:
                if tx_resp.status_code == 401:
                    acc["sessionExpired"] = True

            _save_account_to_db(acc)

        except Exception as e:
            print(f"[banking/refresh] Error for {uid}: {e}")

        updated.append(acc)

    return jsonify({"accounts": updated})
