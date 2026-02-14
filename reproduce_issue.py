import os
import sys
from dotenv import load_dotenv

# Load local .env
load_dotenv()

# Add current directory to path
sys.path.append(os.getcwd())

from services.gemini import categorize_transactions

def test_categorization():
    print("Testing categorization...")
    
    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY not found in environment!")
        return

    # Mock transactions based on what the frontend might send or what's in DB
    transactions = [
        {
            "transaction_id": "test_1",
            "remittance_information": "EDEKA SAGT DANKE",
            "creditor_name": "EDEKA",
            "amount": -12.50
        },
        {
            "transaction_id": "test_2",
            "remittance_information": "PAYPAL UBER BV",
            "creditor_name": "PAYPAL",
            "amount": -15.00
        },
        {
            "transaction_id": "test_3",
            "remittance_information": "Spotify Abbo",
            "creditor_name": "Spotify",
            "amount": -9.99
        }
    ]

    try:
        result = categorize_transactions(transactions)
        print("Result:", result)
    except Exception as e:
        print("Exception during categorization:", e)

if __name__ == "__main__":
    test_categorization()
