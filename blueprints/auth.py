import logging
from functools import wraps
from flask import Blueprint, request, jsonify
import jwt
from config import SECRET_KEY
from database import query
from werkzeug.security import check_password_hash, generate_password_hash

auth_bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # We also need to handle OPTIONS preflight inside standard routing implicitly, Flask CORS handles it.
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            user_id = payload.get("user_id")
            if not user_id:
                return jsonify({"error": "Invalid token payload"}), 401
            
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
            
        # Pass the extracted user_id to the endpoint wrapper
        # We pass it via kwargs so the route function MUST accept user_id
        kwargs["user_id"] = user_id
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route("/auth/login", methods=["POST", "OPTIONS"])
def login():
    if request.method == "OPTIONS":
        return {}, 200
        
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
        
    user = query("SELECT id, password_hash FROM users WHERE username = %(username)s", {"username": username}, fetchone=True)
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401
        
    if not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid credentials"}), 401
        
    token = jwt.encode({"user_id": user["id"]}, SECRET_KEY, algorithm="HS256")
    return jsonify({"token": token, "user_id": user["id"], "username": username}), 200

@auth_bp.route("/auth/register", methods=["POST", "OPTIONS"])
def register():
    if request.method == "OPTIONS":
        return {}, 200
        
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
        
    existing = query("SELECT id FROM users WHERE username = %(username)s", {"username": username}, fetchone=True)
    if existing:
        return jsonify({"error": "Username already exists"}), 400
        
    pwd_hash = generate_password_hash(password)
    query("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, pwd_hash))
    
    user = query("SELECT id FROM users WHERE username = %s", (username,), fetchone=True)
    user_id = user["id"]
    
    # Strictly create ONE cash account for the new user
    cash_account_id = f"CASH_{user_id}"
    query(
        """
        INSERT INTO accounts (account_id, user_id, name, iban, balance, currency, bank_name, type, subtype)
        VALUES (%s, %s, 'Cash Account', 'N/A', 0, 'EUR', 'Cash', 'cash', 'cash')
        """,
        (cash_account_id, user_id)
    )
    
    token = jwt.encode({"user_id": user_id}, SECRET_KEY, algorithm="HS256")
    return jsonify({"token": token, "user_id": user_id, "username": username}), 201

@auth_bp.route("/auth/settings", methods=["GET"])
@login_required
def get_settings(user_id):
    user = query(
        "SELECT gemini_api_key, theme, color_scheme_id, background_style FROM users WHERE id = %s",
        (user_id,), fetchone=True
    )
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({
        "gemini_api_key": user.get("gemini_api_key") or "",
        "theme": user.get("theme") or "dark",
        "color_scheme_id": user.get("color_scheme_id") or "persian-indigo",
        "background_style": user.get("background_style") or "pitch",
    }), 200

@auth_bp.route("/auth/settings", methods=["PUT", "OPTIONS"])
@login_required
def update_settings(user_id):
    data = request.json or {}
    updates = []
    params = []

    if "gemini_api_key" in data:
        updates.append("gemini_api_key = %s")
        params.append(data["gemini_api_key"])
    if "theme" in data:
        updates.append("theme = %s")
        params.append(data["theme"])
    if "color_scheme_id" in data:
        updates.append("color_scheme_id = %s")
        params.append(data["color_scheme_id"])
    if "background_style" in data:
        updates.append("background_style = %s")
        params.append(data["background_style"])

    if updates:
        params.append(user_id)
        query(f"UPDATE users SET {', '.join(updates)} WHERE id = %s", tuple(params))

    return jsonify({"message": "Settings updated"}), 200

