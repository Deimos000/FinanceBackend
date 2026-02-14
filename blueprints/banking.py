"""
Enable Banking integration blueprint.

Endpoints:
  POST /api/banking/auth-url   – get an auth redirect URL
  POST /api/banking/session    – exchange auth code for accounts + data
  POST /api/banking/refresh    – refresh account balances & transactions
"""

import json, time, logging, traceback, requests
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
log = logging.getLogger(__name__)

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
        log.warning("[_save_account_to_db] Skipping – no valid account_id found in %s", list(acc.keys()))
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

    log.info("[_save_account_to_db] Saving account_id=%s, iban=%s, balance=%s, bank=%s",
             account_id, iban, balance, bank_name)

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
    log.info("[_save_account_to_db] ✅ Account %s saved successfully", account_id)


# ── auth-url ──────────────────────────────────────────────

@banking_bp.route("/api/banking/auth-url", methods=["POST"])
def auth_url():
    body = request.get_json(force=True) or {}
    bank_name = body.get("bankName", "Commerzbank")

    log.info("[auth-url] Requesting auth URL for bank=%s", bank_name)

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

    log.info("[auth-url] Enable Banking responded: status=%s", resp.status_code)

    if not resp.ok:
        log.error("[auth-url] Enable Banking error: %s %s", resp.status_code, resp.text)
        return jsonify({"error": f"Enable Banking API returned {resp.status_code}", "details": resp.text}), resp.status_code

    data = resp.json()
    if not data.get("url"):
        log.error("[auth-url] No login URL in response: %s", data)
        return jsonify({"error": "No login URL returned", "details": data}), 500

    log.info("[auth-url] ✅ Auth URL obtained, redirecting user")
    return jsonify({"url": data["url"]})


# ── session ───────────────────────────────────────────────

@banking_bp.route("/api/banking/session", methods=["POST"])
def session():
    body = request.get_json(force=True)
    code = body.get("code")
    if not code:
        return jsonify({"error": "Missing code"}), 400

    log.info("[session] ▶ Starting session exchange. Code prefix: %s...", code[:20] if len(code) > 20 else code)

    headers = _api_headers()

    # Step 1: Exchange auth code for session with Enable Banking
    resp = requests.post(f"{API_BASE}/sessions", headers=headers, json={"code": code})
    log.info("[session] Enable Banking /sessions responded: status=%s", resp.status_code)

    if not resp.ok:
        log.error("[session] Enable Banking /sessions FAILED: status=%s body=%s", resp.status_code, resp.text)
        return jsonify({"error": resp.text}), resp.status_code

    session_data = resp.json()
    accounts = session_data.get("accounts", [])
    log.info("[session] Enable Banking returned %d account(s). Session keys: %s",
             len(accounts), list(session_data.keys()))

    errors = []

    for i, acc in enumerate(accounts):
        uid = acc.get("uid") or acc.get("account_id") or acc.get("iban")
        if not uid or not isinstance(uid, str):
            log.warning("[session] Skipping account #%d – no valid uid. Keys: %s", i, list(acc.keys()))
            continue

        log.info("[session] Processing account #%d: uid=%s, iban=%s", i, uid, acc.get("iban", "N/A"))

        try:
            # ── STEP 2: Save account FIRST (before transactions!) ──
            # The transactions table has a FK to accounts(account_id),
            # so the account row MUST exist before inserting transactions.
            _save_account_to_db(acc)

            # ── STEP 3: Fetch balances & transactions from Enable Banking ──
            log.info("[session] Fetching balances for %s...", uid)
            bal_resp = requests.get(f"{API_BASE}/accounts/{uid}/balances", headers=headers)
            log.info("[session] Balances response: status=%s", bal_resp.status_code)

            log.info("[session] Fetching transactions for %s...", uid)
            # Try to fetch up to 2 years of history. Banks may limit this (e.g. 90 days),
            # but we request the maximum possible.
            date_from = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 730 * 86400))
            tx_resp = requests.get(
                f"{API_BASE}/accounts/{uid}/transactions?date_from={date_from}",
                headers=headers,
            )
            log.info("[session] Transactions response: status=%s", tx_resp.status_code)

            if bal_resp.ok:
                bal_data = bal_resp.json()
                acc["balances"] = bal_data.get("balances", [])
                log.info("[session] Got %d balance entries for %s", len(acc["balances"]), uid)

                # Parse balance and update account in DB with real balance
                if acc["balances"] and isinstance(acc["balances"], list):
                    first = acc["balances"][0]
                    amt_obj = first.get("amount") or first.get("balanceAmount") or first.get("balance_amount") or {}
                    if isinstance(amt_obj, dict) and amt_obj.get("amount"):
                        parsed_bal = float(amt_obj["amount"])
                        acc.setdefault("_parsed", {})["current"] = parsed_bal
                        log.info("[session] Parsed balance for %s: %s", uid, parsed_bal)

                # Re-save account with updated balance
                _save_account_to_db(acc)
            else:
                log.warning("[session] Could not fetch balances for %s: %s %s",
                            uid, bal_resp.status_code, bal_resp.text[:200])

            if tx_resp.ok:
                tx_data = tx_resp.json()
                acc["transactions"] = tx_data.get("transactions", [])
                log.info("[session] Got %d transactions for %s", len(acc["transactions"]), uid)

                saved_count = 0
                failed_count = 0
                for t in acc["transactions"]:
                    try:
                        save_transaction(t, uid)
                        saved_count += 1
                    except Exception as tx_err:
                        failed_count += 1
                        log.error("[session] Failed to save transaction for %s: %s", uid, tx_err)

                log.info("[session] Transactions saved: %d ok, %d failed for %s",
                         saved_count, failed_count, uid)
            else:
                log.warning("[session] Could not fetch transactions for %s: %s %s",
                            uid, tx_resp.status_code, tx_resp.text[:200])

        except Exception as e:
            tb = traceback.format_exc()
            log.error("[session] ❌ Error processing account %s: %s\n%s", uid, e, tb)
            errors.append({"account": uid, "error": str(e)})

    result = {"accounts": accounts}
    if errors:
        result["errors"] = errors
        log.warning("[session] Completed with %d error(s)", len(errors))
    else:
        log.info("[session] ✅ Session completed successfully for %d accounts", len(accounts))

    return jsonify(result)


# ── refresh ───────────────────────────────────────────────

@banking_bp.route("/api/banking/refresh", methods=["POST"])
def refresh():
    body = request.get_json(force=True)
    accounts = body.get("accounts", [])

    if not isinstance(accounts, list):
        return jsonify({"error": "Missing accounts list"}), 400

    log.info("[refresh] ▶ Refreshing %d account(s)", len(accounts))

    headers = _api_headers()

    updated = []
    for acc in accounts:
        uid = acc.get("raw", {}).get("uid") or acc.get("account_id") or acc.get("uid")
        if not uid or not isinstance(uid, str):
            log.warning("[refresh] Skipping account – no valid uid. Keys: %s", list(acc.keys()))
            updated.append(acc)
            continue

        log.info("[refresh] Processing uid=%s", uid)

        try:
            # Save/update account row first
            _save_account_to_db(acc)

            bal_resp = requests.get(f"{API_BASE}/accounts/{uid}/balances", headers=headers)
            tx_resp = requests.get(
                f"{API_BASE}/accounts/{uid}/transactions?date_from="
                + time.strftime("%Y-%m-%d", time.gmtime(time.time() - 730 * 86400)),
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
                        log.info("[refresh] Balance for %s: %s", uid, parsed_bal)

            if tx_resp.ok:
                tx_data = tx_resp.json()
                acc["transactions"] = tx_data.get("transactions", [])
                log.info("[refresh] Got %d transactions for %s", len(acc["transactions"]), uid)
                for t in acc["transactions"]:
                    try:
                        save_transaction(t, acc.get("account_id") or uid)
                    except Exception as tx_err:
                        log.error("[refresh] Failed to save transaction: %s", tx_err)
            else:
                if tx_resp.status_code == 401:
                    acc["sessionExpired"] = True
                    log.warning("[refresh] Session expired for %s", uid)

            _save_account_to_db(acc)

        except Exception as e:
            tb = traceback.format_exc()
            log.error("[refresh] ❌ Error for %s: %s\n%s", uid, e, tb)

        updated.append(acc)

    log.info("[refresh] ✅ Refresh completed for %d account(s)", len(updated))
    return jsonify({"accounts": updated})
