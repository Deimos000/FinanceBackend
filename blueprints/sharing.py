"""
Sandbox sharing blueprint – share sandboxes with friends, manage permissions.
"""

from flask import Blueprint, request, jsonify
from database import query
from blueprints.auth import login_required

sharing_bp = Blueprint("sharing", __name__)


def _check_sandbox_owner(sandbox_id, user_id):
    """Verify the user owns the sandbox. Returns sandbox row or None."""
    return query(
        "SELECT id FROM sandboxes WHERE id = %s AND user_id = %s",
        (sandbox_id, user_id),
        fetchone=True,
    )


def _check_friendship(user_id, friend_id):
    """Check if two users are friends (accepted). Returns True/False."""
    row = query(
        """
        SELECT id FROM friendships
        WHERE ((requester_id = %s AND addressee_id = %s)
            OR (requester_id = %s AND addressee_id = %s))
          AND status = 'accepted'
        """,
        (user_id, friend_id, friend_id, user_id),
        fetchone=True,
    )
    return row is not None


@sharing_bp.route("/api/sandbox/<int:sandbox_id>/shares", methods=["GET"])
@login_required
def get_shares(sandbox_id, user_id):
    """List who a sandbox is shared with. Only the owner can view this."""
    try:
        if not _check_sandbox_owner(sandbox_id, user_id):
            return jsonify({"error": "Sandbox not found or not yours"}), 404

        rows = query(
            """
            SELECT ss.id, ss.shared_with_id, u.username AS shared_with_username,
                   ss.permission, ss.created_at
            FROM sandbox_shares ss
            JOIN users u ON u.id = ss.shared_with_id
            WHERE ss.sandbox_id = %s AND ss.owner_id = %s
            ORDER BY ss.created_at DESC
            """,
            (sandbox_id, user_id),
            fetchall=True,
        )

        shares = []
        for r in (rows or []):
            shares.append({
                "id": r["id"],
                "shared_with_id": r["shared_with_id"],
                "shared_with_username": r["shared_with_username"],
                "permission": r["permission"],
                "created_at": str(r["created_at"]),
            })

        return jsonify({"shares": shares})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sharing_bp.route("/api/sandbox/<int:sandbox_id>/share", methods=["POST"])
@login_required
def share_sandbox(sandbox_id, user_id):
    """Share a sandbox with a friend."""
    data = request.get_json(force=True)
    friend_id = data.get("friend_id")
    permission = data.get("permission", "watch").lower()

    if not friend_id:
        return jsonify({"error": "friend_id is required"}), 400
    if permission not in ("watch", "edit"):
        return jsonify({"error": "permission must be 'watch' or 'edit'"}), 400

    try:
        # Verify ownership
        if not _check_sandbox_owner(sandbox_id, user_id):
            return jsonify({"error": "Sandbox not found or not yours"}), 404

        # Verify friendship
        if not _check_friendship(user_id, friend_id):
            return jsonify({"error": "You can only share with friends"}), 400

        # Check if already shared
        existing = query(
            "SELECT id FROM sandbox_shares WHERE sandbox_id = %s AND shared_with_id = %s",
            (sandbox_id, friend_id),
            fetchone=True,
        )
        if existing:
            # Update permission instead
            query(
                "UPDATE sandbox_shares SET permission = %s WHERE id = %s",
                (permission, existing["id"]),
            )
            return jsonify({"ok": True, "message": "Permission updated"})

        # Create share
        res = query(
            """
            INSERT INTO sandbox_shares (sandbox_id, owner_id, shared_with_id, permission)
            VALUES (%s, %s, %s, %s) RETURNING id
            """,
            (sandbox_id, user_id, friend_id, permission),
            fetchone=True,
        )

        return jsonify({"ok": True, "id": res["id"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sharing_bp.route("/api/sandbox/<int:sandbox_id>/share/<int:share_id>", methods=["PUT"])
@login_required
def update_share(sandbox_id, share_id, user_id):
    """Update permission level for a share."""
    data = request.get_json(force=True)
    permission = data.get("permission", "").lower()

    if permission not in ("watch", "edit"):
        return jsonify({"error": "permission must be 'watch' or 'edit'"}), 400

    try:
        if not _check_sandbox_owner(sandbox_id, user_id):
            return jsonify({"error": "Sandbox not found or not yours"}), 404

        share = query(
            "SELECT id FROM sandbox_shares WHERE id = %s AND sandbox_id = %s AND owner_id = %s",
            (share_id, sandbox_id, user_id),
            fetchone=True,
        )
        if not share:
            return jsonify({"error": "Share not found"}), 404

        query(
            "UPDATE sandbox_shares SET permission = %s WHERE id = %s",
            (permission, share_id),
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sharing_bp.route("/api/sandbox/<int:sandbox_id>/share/<int:share_id>", methods=["DELETE"])
@login_required
def remove_share(sandbox_id, share_id, user_id):
    """Remove a share."""
    try:
        if not _check_sandbox_owner(sandbox_id, user_id):
            return jsonify({"error": "Sandbox not found or not yours"}), 404

        share = query(
            "SELECT id FROM sandbox_shares WHERE id = %s AND sandbox_id = %s AND owner_id = %s",
            (share_id, sandbox_id, user_id),
            fetchone=True,
        )
        if not share:
            return jsonify({"error": "Share not found"}), 404

        query("DELETE FROM sandbox_shares WHERE id = %s", (share_id,))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sharing_bp.route("/api/sandboxes/shared", methods=["GET"])
@login_required
def get_shared_sandboxes(user_id):
    """Get all sandboxes shared with the current user, with correct total_equity."""
    try:
        rows = query(
            """
            SELECT s.id, s.name, s.balance, s.initial_balance, s.created_at,
                   ss.permission, ss.id AS share_id,
                   u.username AS owner_username, ss.owner_id
            FROM sandbox_shares ss
            JOIN sandboxes s ON s.id = ss.sandbox_id
            JOIN users u ON u.id = ss.owner_id
            WHERE ss.shared_with_id = %s
            ORDER BY ss.created_at DESC
            """,
            (user_id,),
            fetchall=True,
        )

        if not rows:
            return jsonify({"sandboxes": []})

        # Collect all sandbox IDs to fetch their portfolios
        sandbox_ids = [r["id"] for r in rows]

        # Fetch all portfolio items for these sandboxes
        all_portfolio = query(
            "SELECT sandbox_id, symbol, quantity, average_buy_price FROM sandbox_portfolio WHERE sandbox_id = ANY(%s)",
            (sandbox_ids,),
            fetchall=True,
        )

        # Build portfolio map and collect symbols
        portfolio_map = {}
        all_symbols = set()
        if all_portfolio:
            for item in all_portfolio:
                sid = item["sandbox_id"]
                if sid not in portfolio_map:
                    portfolio_map[sid] = []
                portfolio_map[sid].append(item)
                all_symbols.add(item["symbol"])

        # Fetch current prices for all symbols at once
        from blueprints.sandbox import _get_current_prices
        prices = _get_current_prices(list(all_symbols))

        results = []
        for r in rows:
            sid = r["id"]
            balance = float(r["balance"])
            initial = float(r["initial_balance"]) if r["initial_balance"] else 10000.0

            # Calculate holdings value
            holdings_value = 0.0
            if sid in portfolio_map:
                for item in portfolio_map[sid]:
                    sym = item["symbol"]
                    qty = float(item["quantity"])
                    price = prices.get(sym, float(item["average_buy_price"]))
                    holdings_value += price * qty

            total_equity = balance + holdings_value

            results.append({
                "id": sid,
                "name": r["name"],
                "balance": balance,
                "initial_balance": initial,
                "total_equity": total_equity,
                "created_at": str(r["created_at"]),
                "permission": r["permission"],
                "share_id": r["share_id"],
                "owner_username": r["owner_username"],
                "owner_id": r["owner_id"],
                "is_shared": True,
            })

        return jsonify({"sandboxes": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

