"""
Thin wrapper around psycopg2 for Supabase PostgreSQL connectivity.
"""

import logging
import psycopg2
import psycopg2.extras
from config import DATABASE_URL

log = logging.getLogger(__name__)


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
    # Create a short label from the SQL for logging (first meaningful line)
    sql_label = sql.strip().split('\n')[0].strip()[:80]
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if fetchone or returning:
                row = cur.fetchone()
                conn.commit()
                log.debug("[query] %s → 1 row", sql_label)
                return dict(row) if row else None
            if fetchall:
                rows = cur.fetchall()
                conn.commit()
                log.debug("[query] %s → %d rows", sql_label, len(rows))
                return [dict(r) for r in rows]
            conn.commit()
            log.debug("[query] %s → %d affected", sql_label, cur.rowcount)
            return cur.rowcount
    except Exception as e:
        conn.rollback()
        log.error("[query] ❌ SQL FAILED: %s | error: %s | params: %s",
                  sql_label, e, str(params)[:200] if params else "None")
        raise
    finally:
        conn.close()
