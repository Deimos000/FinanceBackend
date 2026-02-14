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

from flask import request
@categories_bp.route("/api/categories", methods=["POST"])
def create_category():
    data = request.get_json()
    name = data.get("name")
    color = data.get("color")
    icon = data.get("icon")

    if not name or not color or not icon:
        return jsonify({"error": "Missing fields"}), 400

    query(
        "INSERT INTO categories (name, color, icon) VALUES (%s, %s, %s) ON CONFLICT (name) DO NOTHING",
        (name, color, icon)
    )
    return jsonify({"status": "created", "name": name})
