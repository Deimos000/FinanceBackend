import os
from database import get_conn
import psycopg2.extras

def migrate():
    print("Starting database migration...")
    
    # Check if 'Deimos' user exists, otherwise generate password hash and create user
    # The user wanted password "1130"
    # We will use the custom script output if we can't import werkzeug, but wait, we can just use hashlib or simple if werkzeug is there.
    # The summary said: "Generated a password hash for "Deimos" using a custom script."
    # Let me check if werkzeug is in the environment
    try:
        from werkzeug.security import generate_password_hash
        pwd_hash = generate_password_hash("1130")
    except ImportError:
        # We need another way to generate it
        import hashlib
        # We used the werkzeug default format which is pbkdf2:sha256
        import os, binascii
        salt = binascii.hexlify(os.urandom(16)).decode('utf-8')
        dk = hashlib.pbkdf2_hmac('sha256', b'1130', salt.encode('utf-8'), 600000)
        pwd_hash = f"pbkdf2:sha256:600000${salt}${binascii.hexlify(dk).decode('utf-8')}"
        print("Used custom hash.")

    conn = get_conn()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # 1. Create users table
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """)

            # 2. Insert Deimos user if not exists
            cur.execute("SELECT id FROM users WHERE username = 'Deimos'")
            user = cur.fetchone()
            if not user:
                cur.execute(
                    "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
                    ("Deimos", pwd_hash)
                )
                user_id = cur.fetchone()[0]
                print(f"Created user Deimos with ID: {user_id}")
            else:
                user_id = user[0]
                print(f"User Deimos already exists with ID: {user_id}")
                
            # List of tables that need user_id column
            tables = [
                "accounts", "transactions", "categories", "cash_accounts", 
                "cash_transactions", "debts", "persons", "sandboxes", 
                "sandbox_portfolio", "sandbox_transactions", "wishlist", "budget_settings"
            ]
            
            for table in tables:
                print(f"Processing table {table}...")
                
                # Check if column exists
                cur.execute(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='{table}' and column_name='user_id';
                """)
                if not cur.fetchone():
                    # Add column
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER;")
                    print(f"  Added user_id to {table}")
                    
                    # Update existing rows to belong to Deimos
                    cur.execute(f"UPDATE {table} SET user_id = %s", (user_id,))
                    print(f"  Assigned existing rows in {table} to user_id {user_id}")
                    
                    # Add foreign key constraint
                    cur.execute(f"""
                    ALTER TABLE {table} 
                    ADD CONSTRAINT fk_{table}_user_id 
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
                    """)
                    print(f"  Added FK constraint to {table}")
                else:
                    print(f"  Column user_id already exists on {table}")

        conn.commit()
        print("Migration completed successfully!")
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
