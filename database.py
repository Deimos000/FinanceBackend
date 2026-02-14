"""
Thin wrapper around psycopg2 for Supabase PostgreSQL connectivity.
"""

import psycopg2
import psycopg2.extras
from config import DATABASE_URL


def get_conn():
    """Return a new database connection."""
    return psycopg2.connect(DATABASE_URL)


def query(sql, params=None, fetchone=False, fetchall=False, returning=False):
    """
    Execute *sql* with optional *params* and return results.

    - fetchone=True  → returns a single dict (or None)
    - fetchall=True  → returns a list of dicts
    - returning=True → used with INSERT … RETURNING, returns the row
    - otherwise      → returns the rowcount
    """
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if fetchone or returning:
                row = cur.fetchone()
                conn.commit()
                return dict(row) if row else None
            if fetchall:
                rows = cur.fetchall()
                conn.commit()
                return [dict(r) for r in rows]
            conn.commit()
            return cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
