from flask import Blueprint, jsonify, request
from database import query
from services.gemini import categorize_transactions
import json

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

@statistics_bp.route('/api/stats/categorize', methods=['POST'])
def trigger_categorization():
    """
    Finds uncategorized transactions AND transactions categorized as 'Other'
    and uses Gemini to categorize them.
    """
    # 1. Find target transactions (limit to prevent huge batches)
    # Target: NULL, empty string, or 'Other'
    uncategorized = query("""
        SELECT transaction_id, remittance_information, creditor_name, amount
        FROM transactions
        WHERE (category IS NULL OR category = '' OR category = 'Other')
        ORDER BY booking_date DESC
        LIMIT 50
    """, fetchall=True)
    
    if not uncategorized:
        return jsonify({"message": "No transactions to categorize found", "count": 0})
        
    # 2. Call Gemini
    # Convert rows (dicts) to list for the service
    tx_list = [dict(row) for row in uncategorized]
    category_map = categorize_transactions(tx_list)
    
    if not category_map:
        return jsonify({"message": "AI Categorization failed or returned no results", "count": 0}), 500

    # 3. Update Database
    updated_count = 0
    for tx_id, category in category_map.items():
        # gemini.py says it returns "Other" sometimes.
        # If Gemini returns "Other", we might as well keep it (or original was Other).
        # But if it finds a better match, we update.
        
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
