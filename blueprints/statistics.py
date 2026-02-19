from flask import Blueprint, jsonify, request
from database import query
from services.gemini import categorize_transactions
import json
from datetime import datetime, timedelta

statistics_bp = Blueprint('statistics', __name__)

@statistics_bp.route('/api/stats/category-spending', methods=['GET'])
def category_spending():
    """
    Returns total spending grouped by category for a specific date range.
    """
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # We only care about expenses (negative amounts)
    # Group by category
    sql = """
        SELECT category, SUM(ABS(amount)) as total
        FROM transactions
        WHERE amount < 0
          AND booking_date >= %s
          AND booking_date <= %s
          AND category IS NOT NULL
          AND category != ''
        GROUP BY category
        ORDER BY total DESC
    """
    
    rows = query(sql, (start_date, end_date), fetchall=True)
    
    # Get category colors/icons to enrich response
    categories_ref = query("SELECT name, color, icon FROM categories", fetchall=True)
    cat_map = {c['name']: c for c in categories_ref}
    
    results = []
    for r in rows:
        cat_name = r['category']
        meta = cat_map.get(cat_name, {'color': '#9E9E9E', 'icon': 'help-circle'})
        results.append({
            'name': cat_name,
            'value': float(r['total']),
            'color': meta['color'],
            'icon': meta['icon']
        })
        
    return jsonify(results)

@statistics_bp.route('/api/stats/category-trends', methods=['GET'])
def category_trends():
    """
    Returns daily spending, grouped by category.
    """
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Get daily spending per category
    sql = """
        SELECT category, booking_date, SUM(ABS(amount)) as total
        FROM transactions
        WHERE amount < 0
          AND booking_date >= %s
          AND booking_date <= %s
          AND category IS NOT NULL
          AND category != ''
        GROUP BY category, booking_date
        ORDER BY booking_date ASC
    """
    
    rows = query(sql, (start_date, end_date), fetchall=True)
    
    results = {}
    
    for r in rows:
        cat = r['category']
        if cat not in results:
            results[cat] = []
        
        results[cat].append({
            'date': r['booking_date'].strftime('%Y-%m-%d'),
            'amount': float(r['total'])
        })
        
    return jsonify(results)


@statistics_bp.route('/api/stats/monthly-cashflow', methods=['GET'])
def monthly_cashflow():
    """
    Returns monthly income and spending for the last N months.
    Each item: { month: "YYYY-MM", income: float, spending: float }
    """
    months = request.args.get('months', 6, type=int)
    cutoff = (datetime.utcnow() - timedelta(days=months * 31)).strftime('%Y-%m-%d')

    rows = query("""
        SELECT
            TO_CHAR(booking_date, 'YYYY-MM') AS month,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS income,
            SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) AS spending
        FROM transactions
        WHERE booking_date >= %s
        GROUP BY TO_CHAR(booking_date, 'YYYY-MM')
        ORDER BY month ASC
    """, (cutoff,), fetchall=True)

    results = []
    for r in rows:
        results.append({
            'month': r['month'],
            'income': float(r['income'] or 0),
            'spending': float(r['spending'] or 0),
        })

    return jsonify(results)


# ── Budget Settings ────────────────────────────────────────

@statistics_bp.route('/api/budget/settings', methods=['GET'])
def get_budget_settings():
    """Returns the global budget settings (monthly income target)."""
    row = query("SELECT monthly_income FROM budget_settings ORDER BY id LIMIT 1", fetchone=True)
    if not row:
        return jsonify({'monthly_income': 0})
    return jsonify({'monthly_income': float(row['monthly_income'])})


@statistics_bp.route('/api/budget/settings', methods=['PUT'])
def update_budget_settings():
    """Updates the monthly income target."""
    data = request.get_json()
    monthly_income = data.get('monthly_income', 0)

    # Upsert: update existing row or insert if empty
    existing = query("SELECT id FROM budget_settings ORDER BY id LIMIT 1", fetchone=True)
    if existing:
        query(
            "UPDATE budget_settings SET monthly_income = %s, updated_at = NOW() WHERE id = %s",
            (monthly_income, existing['id'])
        )
    else:
        query(
            "INSERT INTO budget_settings (monthly_income) VALUES (%s)",
            (monthly_income,)
        )

    return jsonify({'status': 'updated', 'monthly_income': monthly_income})


# ── Category Budgets ───────────────────────────────────────

@statistics_bp.route('/api/budget/categories', methods=['GET'])
def get_category_budgets():
    """Returns all categories with their monthly_budget limits."""
    rows = query(
        "SELECT name, color, icon, COALESCE(monthly_budget, 0) as monthly_budget FROM categories ORDER BY name",
        fetchall=True
    )
    results = []
    for r in rows:
        results.append({
            'name': r['name'],
            'color': r['color'],
            'icon': r['icon'],
            'monthly_budget': float(r['monthly_budget'] or 0),
        })
    return jsonify(results)


@statistics_bp.route('/api/budget/categories/<string:category_name>', methods=['PUT'])
def update_category_budget(category_name):
    """Updates the monthly_budget for a specific category."""
    data = request.get_json()
    monthly_budget = data.get('monthly_budget', 0)

    query(
        "UPDATE categories SET monthly_budget = %s WHERE name = %s",
        (monthly_budget, category_name)
    )
    return jsonify({'status': 'updated', 'name': category_name, 'monthly_budget': monthly_budget})


# ── Categorization ─────────────────────────────────────────

@statistics_bp.route('/api/stats/categorize', methods=['POST'])
def trigger_categorization():
    """
    Finds uncategorized transactions AND transactions categorized as 'Other'
    and uses Gemini to categorize them.
    """
    uncategorized = query("""
        SELECT transaction_id, remittance_information, creditor_name, amount
        FROM transactions
        WHERE (category IS NULL OR category = '' OR category = 'Other')
        ORDER BY booking_date DESC
        LIMIT 50
    """, fetchall=True)
    
    if not uncategorized:
        return jsonify({"message": "No transactions to categorize found", "count": 0})
        
    tx_list = [dict(row) for row in uncategorized]
    category_map = categorize_transactions(tx_list)
    
    if not category_map:
        return jsonify({"message": "AI Categorization failed or returned no results", "count": 0}), 500

    updated_count = 0
    for tx_id, category in category_map.items():
        query("""
            UPDATE transactions
            SET category = %s
            WHERE transaction_id = %s
        """, (category, tx_id))
        updated_count += 1
        
    return jsonify({
        "message": "Categorization complete", 
        "processed": len(uncategorized),
        "updated": updated_count,
        "details": category_map
    })
