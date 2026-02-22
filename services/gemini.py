import os
import json
from config import GEMINI_API_KEY

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    print("Warning: google-generativeai module not found. AI features disabled.")

if HAS_GEMINI and GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Failed to configure Gemini: {e}")

def categorize_transactions(transactions, user_id=None):
    """
    Takes a list of transaction dictionaries (description, amount, etc.)
    and returns a list of categories corresponding to them.
    We'll ask Gemini to return a JSON array of category names.
    
    Allowed Categories:
    Groceries, Shopping, Transport, Income, Utilities, Entertainment, Health, Dining, Other
    """
    if not HAS_GEMINI:
        return {}

    api_key_to_use = GEMINI_API_KEY

    if user_id:
        from database import query
        user_record = query("SELECT gemini_api_key FROM users WHERE id = %s", (user_id,), fetchone=True)
        if user_record and user_record.get("gemini_api_key"):
            api_key_to_use = user_record["gemini_api_key"]

    if not transactions or not api_key_to_use:
        return []

    try:
        genai.configure(api_key=api_key_to_use)
    except Exception as e:
        print(f"Failed to configure Gemini with specific key: {e}")
        return {}

    model = genai.GenerativeModel('gemini-2.5-flash')

    # Prepare specific minimal data for the prompt to save tokens (and privacy)
    # We essentially want just the description/remittance info.
    summary_list = []
    for t in transactions:
        desc = t.get("remittance_information") or t.get("creditor_name") or "Unknown"
        amount = t.get("amount")
        summary_list.append(f"ID: {t['transaction_id']}, Desc: {desc}, Amount: {amount}")

    prompt = f"""
    You are a financial assistant. I will provide a list of transactions.
    Map each one to exactly one of these categories:
    [Groceries, Shopping, Transport, Income, Utilities, Entertainment, Health, Dining, Other]
    
    Return ONLY a raw JSON object mapping transaction IDs to categories. 
    Format:
    {{
      "transaction_id_1": "CategoryName",
      "transaction_id_2": "CategoryName"
    }}

    Transactions:
    {json.dumps(summary_list, indent=2)}
    """

    try:
        response = model.generate_content(prompt)
        text_response = response.text.replace('```json', '').replace('```', '').strip()
        category_map = json.loads(text_response)
        return category_map
    except Exception as e:
        print(f"Gemini Error during generation: {e}")
        import traceback
        traceback.print_exc()
        return {}
