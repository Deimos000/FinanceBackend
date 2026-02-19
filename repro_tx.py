import hashlib
import base64
import json
import re

# Mocks
def query(sql, params=None, fetchone=False, fetchall=False, returning=False):
    print(f"MOCK QUERY: {sql[:50]}... params={params}")
    if "SELECT 1" in sql:
        return []
    return 1

# Copied from transactions.py (helper functions)
def _legacy_stable_id(t, account_id):
    tid = t.get("transaction_id") or t.get("transactionId") or t.get("entry_reference")
    if tid:
        return str(tid)
    raw = f"{account_id}-{t.get('booking_date','')}-{t.get('amount',0)}"
    return base64.b64encode(raw.encode()).decode()

def _robust_stable_id(t, account_id):
    # 1. Prefer explicit bank ID if available
    tid = t.get("transaction_id") or t.get("transactionId") or t.get("entry_reference")
    if tid:
        return str(tid)

    # 2. Construct unique string from fields
    amount = t.get("amount")
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
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def save_transaction(t, account_id):
    print(f"\n--- Saving Transaction for {account_id} ---")
    try:
        amount = 0.0
        ta = t.get("transaction_amount") or {}
        if ta.get("amount"):
            amount = float(ta["amount"])
        elif isinstance(t.get("amount"), (int, float)):
            amount = float(t["amount"])
        
        # NOTE: What if t.get("amount") is a string?
        # Added check for reproduction:
        elif isinstance(t.get("amount"), str):
            print("WARNING: Amount is string, logic might skip it or fail if not handled")
            # In original code, it falls through and amount stays 0.0

        indicator = t.get("credit_debit_indicator", "")
        if indicator in ("DBIT", "D"):
            amount = -abs(amount)
        elif indicator in ("CRDT", "C"):
            amount = abs(amount)

        new_id = _robust_stable_id(t, account_id)
        old_id = _legacy_stable_id(t, account_id)
        
        print(f"Parsed Amount: {amount}")
        print(f"New ID: {new_id}")

        # ... (DB Logic mocked) ...
        return True
    except Exception as e:
        print(f"EXCEPTION: {e}")
        return False

# Test Cases
test_data = [
    # Case 1: Standard Enable Banking format (transactionAmount dict)
    {
        "transaction_amount": {"amount": "123.45", "currency": "EUR"},
        "booking_date": "2023-01-01",
        "remittance_information": ["Payment Ref"]
    },
    # Case 2: Amount as direct value (legacy/other)
    {
        "amount": 50.0,
        "booking_date": "2023-01-02"
    },
    # Case 3: Amount as string (potential issue?)
    {
        "amount": "99.99",
        "booking_date": "2023-01-03"
    },
    # Case 4: Amount as dict (common in some APIs but handled by transaction_amount check?)
    {
        "amount": {"amount": "10.00", "currency": "EUR"},
        "booking_date": "2023-01-04"
    },
    # Case 5: DBIT indicator
    {
        "transaction_amount": {"amount": "100.00", "currency": "EUR"},
        "credit_debit_indicator": "DBIT",
        "booking_date": "2023-01-05"
    }
]

print("Running Reproduction Tests...")
for i, t in enumerate(test_data):
    save_transaction(t, f"acc_{i}")
