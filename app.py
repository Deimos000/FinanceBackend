"""
Finance Backend – Flask entry point.
"""

import logging
import sys

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
from blueprints.statistics import statistics_bp
from blueprints.wishlist import wishlist_bp


def create_app():
    # ── Configure logging for Cloud Run ──
    # Cloud Run captures stdout/stderr → send structured logs there
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )

    app = Flask(__name__)

    # Also set Flask's own logger to INFO
    app.logger.setLevel(logging.INFO)

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
    app.register_blueprint(statistics_bp)
    app.register_blueprint(wishlist_bp)

    # Health check
    @app.route("/health")
    def health():
        return {"status": "ok"}

    app.logger.info("Finance Backend started. Blueprints registered.")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=PORT, debug=True)
