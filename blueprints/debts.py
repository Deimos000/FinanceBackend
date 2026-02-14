"""
Debts blueprint – persons, debts, sub-debts CRUD.
"""

from flask import Blueprint, request, jsonify
from database import query

debts_bp = Blueprint("debts", __name__)


# ── GET ────────────────────────────────────────────────────

@debts_bp.route("/api/debts", methods=["GET"])
def get_debts():
    """
    ?type=summary → people with net balance
    ?type=list    → all debts with sub_debts & remaining amounts
    """
    qtype = request.args.get("type", "summary")

    if qtype == "summary":
        people = query("SELECT * FROM persons ORDER BY name", fetchall=True)

        summaries = []
        for person in people:
            debts = query(
                "SELECT * FROM debts WHERE person_id = %s",
                (person["id"],),
                fetchall=True,
            )
            net_balance = 0.0
            for d in debts:
                sub_sum = query(
                    "SELECT COALESCE(SUM(amount), 0) AS total FROM sub_debts WHERE debt_id = %s",
                    (d["id"],),
                    fetchone=True,
                )
                paid = float(sub_sum["total"])
                remaining = float(d["amount"]) - paid
                if d["type"] == "OWED_TO_ME":
                    net_balance += remaining
                else:
                    net_balance -= remaining

            summaries.append({
                **person,
                "created_at": str(person["created_at"]),
                "netBalance": net_balance,
            })

        return jsonify(summaries)

    if qtype == "list":
        filter_type = request.args.get("filter")

        sql = """
            SELECT d.*, p.name AS person_name
            FROM debts d
            JOIN persons p ON d.person_id = p.id
        """
        params = []
        if filter_type:
            sql += " WHERE d.type = %s"
            params.append(filter_type)
        sql += " ORDER BY d.created_at DESC"

        debts = query(sql, params or None, fetchall=True)

        result = []
        for d in debts:
            sub_sum = query(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM sub_debts WHERE debt_id = %s",
                (d["id"],),
                fetchone=True,
            )
            paid = float(sub_sum["total"])
            sub_debts = query(
                "SELECT * FROM sub_debts WHERE debt_id = %s ORDER BY created_at DESC",
                (d["id"],),
                fetchall=True,
            )
            for sd in sub_debts:
                sd["amount"] = float(sd["amount"])
                sd["created_at"] = str(sd["created_at"])

            result.append({
                **d,
                "amount": float(d["amount"]),
                "created_at": str(d["created_at"]),
                "paid_amount": paid,
                "remaining_amount": float(d["amount"]) - paid,
                "sub_debts": sub_debts,
            })

        return jsonify(result)

    return jsonify({"error": "Invalid type param"}), 400


# ── POST (action-based) ───────────────────────────────────

@debts_bp.route("/api/debts", methods=["POST"])
def create():
    body = request.get_json(force=True)
    action = body.get("action")

    if action == "create_person":
        name = body.get("name", "").strip()
        if not name:
            return jsonify({"error": "Name required"}), 400
        row = query(
            "INSERT INTO persons (name) VALUES (%s) RETURNING id, name",
            (name,),
            returning=True,
        )
        return jsonify(row)

    if action == "create_debt":
        row = query(
            """
            INSERT INTO debts (person_id, type, amount, description)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (
                body["person_id"],
                body["type"],
                body["amount"],
                body.get("description", ""),
            ),
            returning=True,
        )
        return jsonify(row)

    if action == "create_sub_debt":
        debt_id = body["debt_id"]
        amount = body["amount"]
        note = body.get("note", "")

        row = query(
            "INSERT INTO sub_debts (debt_id, amount, note) VALUES (%s, %s, %s) RETURNING id",
            (debt_id, amount, note),
            returning=True,
        )

        # Check if debt is fully paid → auto-delete
        debt = query("SELECT amount FROM debts WHERE id = %s", (debt_id,), fetchone=True)
        sub_total = query(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM sub_debts WHERE debt_id = %s",
            (debt_id,),
            fetchone=True,
        )
        remaining = float(debt["amount"]) - float(sub_total["total"])

        deleted = False
        if remaining <= 0:
            query("DELETE FROM sub_debts WHERE debt_id = %s", (debt_id,))
            query("DELETE FROM debts WHERE id = %s", (debt_id,))
            deleted = True

        return jsonify({"id": row["id"], "deleted": deleted})

    return jsonify({"error": "Invalid action"}), 400


# ── DELETE ─────────────────────────────────────────────────

@debts_bp.route("/api/debts/<int:debt_id>", methods=["DELETE"])
def delete_debt(debt_id):
    query("DELETE FROM sub_debts WHERE debt_id = %s", (debt_id,))
    deleted = query("DELETE FROM debts WHERE id = %s", (debt_id,))
    if deleted == 0:
        return jsonify({"error": "Debt not found"}), 404
    return jsonify({"ok": True})
