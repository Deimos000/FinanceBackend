"""
Finance Backend – Flask entry point.
"""

from flask import Flask
from flask_cors import CORS

from config import PORT
from blueprints.accounts import accounts_bp
from blueprints.transactions import transactions_bp
from blueprints.debts import debts_bp
from blueprints.categories import categories_bp
from blueprints.cash import cash_bp
from blueprints.banking import banking_bp
from blueprints.stocks import stocks_bp


def create_app():
    app = Flask(__name__)

    # Allow requests from any origin (Expo dev server, web, mobile, etc.)
    CORS(app)

    # Register blueprints
    app.register_blueprint(accounts_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(debts_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(cash_bp)
    app.register_blueprint(banking_bp)
    app.register_blueprint(stocks_bp)

    # Health check
    @app.route("/health")
    def health():
        return {"status": "ok"}

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=PORT, debug=True)
