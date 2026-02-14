"""
Categories blueprint – list transaction categories.
"""

from flask import Blueprint, jsonify
from database import query

categories_bp = Blueprint("categories", __name__)


@categories_bp.route("/api/categories", methods=["GET"])
def get_categories():
    rows = query("SELECT name, color, icon FROM categories ORDER BY name", fetchall=True)
    # Add a placeholder 'total' the frontend expects
    for r in rows:
        r["total"] = 0
    return jsonify(rows)
