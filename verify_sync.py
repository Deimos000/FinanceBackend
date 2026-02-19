
import sys
import unittest
from unittest.mock import MagicMock, patch
import json

# Add properties path to sys.path if needed, but since we are in root (likely), it should be fine.
# We'll assume the script is run from c:\Users\denis\Desktop\FinanceBackend

# Mock database.query BEFORE importing blueprints
sys.modules['database'] = MagicMock()
from blueprints.transactions import save_transaction

class TestSyncLogic(unittest.TestCase):
    def setUp(self):
        # Reset mock
        sys.modules['database'].query.reset_mock()
        self.mock_query = sys.modules['database'].query

    def test_save_new_transaction(self):
        """Test saving a completely new transaction."""
        t = {
            "transactionId": "tx123",
            "amount": {"amount": "10.00", "currency": "EUR"},
            "bookingDate": "2023-01-01",
            "creditorName": "Shop A"
        }
        
        # Mock query responses:
        # 1. Check old ID -> None (not found)
        # 2. Check new ID -> None (not found)
        # 3. Insert -> None
        self.mock_query.side_effect = [None, None, None]
        
        is_new = save_transaction(t, "acc1")
        
        self.assertTrue(is_new, "Should be marked as new")
        # Ensure insert was called
        self.assertEqual(self.mock_query.call_count, 3)
        # Last call should be INSERT
        self.assertIn("INSERT INTO transactions", self.mock_query.call_args_list[2][0][0])

    def test_save_existing_transaction(self):
        """Test saving an existing transaction."""
        t = {
            "transactionId": "tx123",
            "amount": {"amount": "10.00", "currency": "EUR"},
            "bookingDate": "2023-01-01"
        }
        
        # Mock query responses:
        # 1. Check old ID -> None
        # 2. Check new ID -> {'transaction_id': 'tx123'} (Found!)
        self.mock_query.side_effect = [None, {'transaction_id': 'tx123'}]
        
        is_new = save_transaction(t, "acc1")
        
        self.assertFalse(is_new, "Should be marked as existing")
        # Should NOT insert
        self.assertEqual(self.mock_query.call_count, 2)

    def test_migrate_old_transaction(self):
        """Test migration of old ID to new ID."""
        t = {
            "transactionId": "tx123", # New ID style
            # Missing other fields that might have made up old ID
        }
        
        # Mock query responses:
        # 1. Check old ID -> Found!
        # 2. Check new ID -> None (New ID not found yet)
        # 3. Update ID (MIGRATE)
        # 4. Return
        self.mock_query.side_effect = [
            {'transaction_id': 'old_style_id'}, # old found
            None, # new not found
            None # update
        ]
        
        is_new = save_transaction(t, "acc1")
        
        # After migration, it returns False (because it WAS existing, just migrated)
        self.assertFalse(is_new, "Should be marked as existing after migration")
        
        # Check if UPDATE was called
        calls = self.mock_query.call_args_list
        self.assertIn("UPDATE transactions SET transaction_id", calls[2][0][0])

if __name__ == '__main__':
    unittest.main()
