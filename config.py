"""
Configuration - reads from environment variables
"""
import os


def _parse_admin_ids(raw: str):
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            pass
    return ids


API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Comma separated list of Telegram user IDs allowed to use the bot,
# e.g. ADMIN_IDS="123456789,987654321"
ADMIN_IDS = _parse_admin_ids(os.environ.get("ADMIN_IDS", ""))

# MongoDB connection
MONGO_URI = os.environ.get("MONGO_URI", "")
DB_NAME = os.environ.get("DB_NAME", "url_shortener")

# Public base URL of the deployed service, no trailing slash.
# e.g. https://domain.app
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")

# Length of the randomly generated short code
SHORT_CODE_LENGTH = int(os.environ.get("SHORT_CODE_LENGTH", 6))

# Optional API key to protect the public HTTP shortening endpoint
# (GET /api?url=...). If left empty, the endpoint is open to anyone.
# If set, callers must pass it as ?api_key=... or an "X-API-Key" header.
API_KEY = os.environ.get("API_KEY", "")
