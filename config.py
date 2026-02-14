import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ──────────────────────────────────────────────
# For testing: hardcoded.  For production: set DATABASE_URL env var.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres.ipklmfxfvbayxwsbazpj:SuperAdminPassword.@aws-1-eu-central-1.pooler.supabase.com:6543/postgres",
)

# ── Enable Banking ────────────────────────────────────────
ENABLE_BANKING_APP_ID = os.environ.get(
    "ENABLE_BANKING_APP_ID",
    "da29a728-39e7-494d-9913-987087276661",
)

# The private key is read from env in production (single-line with \n) or
# falls back to the hardcoded literal used during testing.
_DEFAULT_KEY = """-----BEGIN PRIVATE KEY-----
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
SqIKLENg196UJCofV3Utat2bo7EqdQ==
-----END PRIVATE KEY-----"""

ENABLE_BANKING_PRIVATE_KEY = os.environ.get("ENABLE_BANKING_PRIVATE_KEY", _DEFAULT_KEY)
# When stored in env as single-line, the literal \\n must become real newlines
if "\\n" in ENABLE_BANKING_PRIVATE_KEY:
    ENABLE_BANKING_PRIVATE_KEY = ENABLE_BANKING_PRIVATE_KEY.replace("\\n", "\n")

ENABLE_BANKING_REDIRECT_URL = os.environ.get(
    "ENABLE_BANKING_REDIRECT_URL", "https://localhost/"
)

# ── Gemini / AI ───────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDpY88195Xs2VPBm2sxcbJ2o4e89QkQot0")

# ── Flask ─────────────────────────────────────────────────
PORT = int(os.environ.get("PORT", 5000))
