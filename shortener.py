"""
shortener.py — random short-code generation and URL validation, plus the
high level "create a short link" flow that talks to the database.
"""

import secrets
import string
from urllib.parse import urlparse

import db
from config import BASE_URL, SHORT_CODE_LENGTH

_ALPHABET = string.ascii_letters + string.digits


def generate_code(length: int = None) -> str:
    """Generate a random alphanumeric code, e.g. 'A28UO'."""
    length = length or SHORT_CODE_LENGTH
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def is_valid_url(url: str) -> bool:
    """Basic validation: must be http(s) and have a network location."""
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def build_short_url(code: str) -> str:
    return f"{BASE_URL}/{code}"


async def create_short_link(original_url: str, created_by: int) -> str:
    """
    Create (or reuse) a short link for original_url and return the full
    shortened URL, e.g. https://domain.app/A28UO
    """
    original_url = original_url.strip()

    # Reuse an existing short link for the same admin + URL instead of
    # generating duplicate codes for the same destination.
    existing = await db.find_existing_link(original_url, created_by)
    if existing:
        return build_short_url(existing["_id"])

    # Try generating a unique code, retrying on the rare collision.
    for _ in range(10):
        code = generate_code()
        saved = await db.save_link(code, original_url, created_by)
        if saved:
            return build_short_url(code)

    raise RuntimeError("Failed to generate a unique short code after multiple attempts.")
