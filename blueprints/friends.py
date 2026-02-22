"""
Friends blueprint – search users, send/accept/reject friend requests, list friends.
"""

from flask import Blueprint, request, jsonify
from database import query
from blueprints.auth import login_required

friends_bp = Blueprint("friends", __name__)


@friends_bp.route("/api/friends/search", methods=["GET"])
@login_required
def search_users(user_id):
    """Search users by username (partial match). Excludes the current user."""
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify({"users": []})

    try:
        rows = query(
            """
            SELECT id, username FROM users
            WHERE username ILIKE %s AND id != %s
            ORDER BY username
            LIMIT 20
            """,
            (f"%{q}%", user_id),
            fetchall=True,
        )
        users = [{"id": r["id"], "username": r["username"]} for r in (rows or [])]
        return jsonify({"users": users})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@friends_bp.route("/api/friends/request", methods=["POST"])
@login_required
def send_friend_request(user_id):
    """Send a friend request to another user by username."""
    data = request.get_json(force=True)
    username = data.get("username", "").strip()

    if not username:
        return jsonify({"error": "Username is required"}), 400

    try:
        # Find the addressee
        addressee = query(
            "SELECT id FROM users WHERE username = %s", (username,), fetchone=True
        )
        if not addressee:
            return jsonify({"error": "User not found"}), 404

        addressee_id = addressee["id"]

        if addressee_id == user_id:
            return jsonify({"error": "Cannot send friend request to yourself"}), 400

        # Check if friendship already exists in either direction
        existing = query(
            """
            SELECT id, status FROM friendships
            WHERE (requester_id = %s AND addressee_id = %s)
               OR (requester_id = %s AND addressee_id = %s)
            """,
            (user_id, addressee_id, addressee_id, user_id),
            fetchone=True,
        )

        if existing:
            if existing["status"] == "accepted":
                return jsonify({"error": "Already friends"}), 400
            if existing["status"] == "pending":
                return jsonify({"error": "Friend request already pending"}), 400
            if existing["status"] == "rejected":
                # Allow re-sending after rejection – update existing row
                query(
                    "UPDATE friendships SET status = 'pending', requester_id = %s, addressee_id = %s, updated_at = NOW() WHERE id = %s",
                    (user_id, addressee_id, existing["id"]),
                )
                return jsonify({"ok": True, "message": "Friend request sent"})

        # Create new friendship
        query(
            "INSERT INTO friendships (requester_id, addressee_id, status) VALUES (%s, %s, 'pending')",
            (user_id, addressee_id),
        )
        return jsonify({"ok": True, "message": "Friend request sent"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@friends_bp.route("/api/friends/requests", methods=["GET"])
@login_required
def get_friend_requests(user_id):
    """Get pending incoming friend requests for the current user."""
    try:
        rows = query(
            """
            SELECT f.id, f.requester_id, u.username AS requester_username, f.created_at
            FROM friendships f
            JOIN users u ON u.id = f.requester_id
            WHERE f.addressee_id = %s AND f.status = 'pending'
            ORDER BY f.created_at DESC
            """,
            (user_id,),
            fetchall=True,
        )

        requests_list = []
        for r in (rows or []):
            requests_list.append({
                "id": r["id"],
                "requester_id": r["requester_id"],
                "requester_username": r["requester_username"],
                "created_at": str(r["created_at"]),
            })

        # Also get outgoing pending requests
        outgoing = query(
            """
            SELECT f.id, f.addressee_id, u.username AS addressee_username, f.created_at
            FROM friendships f
            JOIN users u ON u.id = f.addressee_id
            WHERE f.requester_id = %s AND f.status = 'pending'
            ORDER BY f.created_at DESC
            """,
            (user_id,),
            fetchall=True,
        )

        outgoing_list = []
        for r in (outgoing or []):
            outgoing_list.append({
                "id": r["id"],
                "addressee_id": r["addressee_id"],
                "addressee_username": r["addressee_username"],
                "created_at": str(r["created_at"]),
            })

        return jsonify({"incoming": requests_list, "outgoing": outgoing_list})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@friends_bp.route("/api/friends/respond", methods=["POST"])
@login_required
def respond_to_request(user_id):
    """Accept or reject a friend request."""
    data = request.get_json(force=True)
    friendship_id = data.get("friendship_id")
    action = data.get("action", "").lower()  # 'accept' or 'reject'

    if not friendship_id or action not in ("accept", "reject"):
        return jsonify({"error": "friendship_id and action (accept/reject) required"}), 400

    try:
        # Verify this request is addressed to the current user
        friendship = query(
            "SELECT id, addressee_id FROM friendships WHERE id = %s AND status = 'pending'",
            (friendship_id,),
            fetchone=True,
        )
        if not friendship:
            return jsonify({"error": "Friend request not found"}), 404

        if friendship["addressee_id"] != user_id:
            return jsonify({"error": "Not authorized to respond to this request"}), 403

        new_status = "accepted" if action == "accept" else "rejected"
        query(
            "UPDATE friendships SET status = %s, updated_at = NOW() WHERE id = %s",
            (new_status, friendship_id),
        )

        return jsonify({"ok": True, "status": new_status})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@friends_bp.route("/api/friends", methods=["GET"])
@login_required
def get_friends(user_id):
    """Get all accepted friends."""
    try:
        rows = query(
            """
            SELECT
                f.id AS friendship_id,
                CASE WHEN f.requester_id = %s THEN f.addressee_id ELSE f.requester_id END AS friend_id,
                CASE WHEN f.requester_id = %s THEN u2.username ELSE u1.username END AS friend_username,
                f.created_at
            FROM friendships f
            JOIN users u1 ON u1.id = f.requester_id
            JOIN users u2 ON u2.id = f.addressee_id
            WHERE (f.requester_id = %s OR f.addressee_id = %s)
              AND f.status = 'accepted'
            ORDER BY f.created_at DESC
            """,
            (user_id, user_id, user_id, user_id),
            fetchall=True,
        )

        friends = []
        for r in (rows or []):
            friends.append({
                "friendship_id": r["friendship_id"],
                "friend_id": r["friend_id"],
                "friend_username": r["friend_username"],
                "since": str(r["created_at"]),
            })

        return jsonify({"friends": friends})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@friends_bp.route("/api/friends/<int:friendship_id>", methods=["DELETE"])
@login_required
def remove_friend(friendship_id, user_id):
    """Remove a friend (both directions)."""
    try:
        friendship = query(
            "SELECT id FROM friendships WHERE id = %s AND (requester_id = %s OR addressee_id = %s)",
            (friendship_id, user_id, user_id),
            fetchone=True,
        )
        if not friendship:
            return jsonify({"error": "Friendship not found"}), 404

        # Also clean up any sandbox shares between these users
        query(
            """
            DELETE FROM sandbox_shares
            WHERE (owner_id = %s AND shared_with_id IN (
                SELECT CASE WHEN requester_id = %s THEN addressee_id ELSE requester_id END
                FROM friendships WHERE id = %s
            ))
            OR (shared_with_id = %s AND owner_id IN (
                SELECT CASE WHEN requester_id = %s THEN addressee_id ELSE requester_id END
                FROM friendships WHERE id = %s
            ))
            """,
            (user_id, user_id, friendship_id, user_id, user_id, friendship_id),
        )

        query("DELETE FROM friendships WHERE id = %s", (friendship_id,))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
