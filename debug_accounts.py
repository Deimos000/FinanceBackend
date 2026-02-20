from database import query
import json

rows = query("SELECT account_id, name, iban, bank_name FROM accounts", fetchall=True)
print(json.dumps(rows, indent=2, default=str))
