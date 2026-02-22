"""
Categories blueprint – list transaction categories.
"""

from flask import Blueprint, jsonify, request
from database import query
from blueprints.auth import login_required

categories_bp = Blueprint("categories", __name__)


@categories_bp.route("/api/categories", methods=["GET"])
@login_required
def get_categories(user_id):
    rows = query("SELECT name, color, icon FROM categories WHERE user_id = %s OR user_id IS NULL ORDER BY name", (user_id,), fetchall=True)
    # Add a placeholder 'total' the frontend expects
    for r in rows:
        r["total"] = 0
    return jsonify(rows)

@categories_bp.route("/api/categories", methods=["POST"])
@login_required
def create_category(user_id):
    data = request.get_json()
    name = data.get("name")
    color = data.get("color")
    icon = data.get("icon")

    if not name or not color or not icon:
        return jsonify({"error": "Missing fields"}), 400

    query(
        "INSERT INTO categories (name, color, icon, user_id) VALUES (%s, %s, %s, %s) ON CONFLICT (name) DO NOTHING",
        (name, color, icon, user_id)
    )
    return jsonify({"status": "created", "name": name})
