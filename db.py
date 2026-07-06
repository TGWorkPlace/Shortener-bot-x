"""
db.py — MongoDB access layer for the URL shortener.

Stores documents of the shape:
{
    "_id": "A28UO",              # the short code, also used as unique key
    "original_url": "https://...",
    "created_by": 123456789,     # telegram user id of the admin who created it
    "created_at": datetime,
    "clicks": 0
}
"""

import logging
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from config import MONGO_URI, DB_NAME

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient = None
_db = None
_links = None


async def connect():
    """Initialize the MongoDB connection. Call once on startup."""
    global _client, _db, _links
    _client = AsyncIOMotorClient(MONGO_URI)
    _db = _client[DB_NAME]
    _links = _db["links"]
    # _id already acts as a unique index, no extra index needed for lookups.
    await _client.admin.command("ping")
    logger.info("Connected to MongoDB (%s)", DB_NAME)
    await _drop_stray_indexes()


async def _drop_stray_indexes():
    """
    Defensive cleanup: this schema only relies on the default unique index
    on _id. If an old/unrelated index (e.g. a leftover 'code_1' unique index
    from a previous schema) exists on this collection, every insert that
    doesn't populate that field will collide on 'null' and fail forever.
    Drop anything that isn't the default _id index.
    """
    try:
        indexes = await _links.index_information()
    except Exception as e:
        logger.warning("Could not read indexes on 'links': %s", e)
        return

    for name in indexes:
        if name == "_id_":
            continue
        try:
            await _links.drop_index(name)
            logger.warning("Dropped stray index '%s' on 'links' collection.", name)
        except Exception as e:
            logger.warning("Could not drop stray index '%s': %s", name, e)


async def close():
    """Close the MongoDB connection. Call on shutdown."""
    if _client is not None:
        _client.close()
        logger.info("MongoDB connection closed.")


async def save_link(code: str, original_url: str, created_by: int) -> bool:
    """
    Attempt to insert a new short link. Returns True on success,
    False only if the *code itself* (_id) already exists, in which case
    the caller should retry with a new code.

    Any other duplicate-key violation (e.g. an unexpected unique index on
    original_url) is a real misconfiguration, not a code collision, so it
    is logged clearly and re-raised instead of being silently retried.
    """
    try:
        await _links.insert_one({
            "_id": code,
            "original_url": original_url,
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc),
            "clicks": 0,
        })
        return True
    except DuplicateKeyError as e:
        key_pattern = (getattr(e, "details", None) or {}).get("keyPattern", {})
        if "_id" in key_pattern or not key_pattern:
            # Genuine code collision — extremely rare, safe to retry.
            return False
        # Some other unique index (e.g. on original_url) is rejecting this
        # insert. Retrying with a new random code will never fix this.
        logger.error(
            "Duplicate key on unexpected index %s while saving link for %s. "
            "Check your MongoDB collection for a stray unique index (e.g. on "
            "'original_url') — it should not exist and should be dropped.",
            key_pattern, original_url,
        )
        raise


async def get_link(code: str):
    """Return the document for a short code, or None if it doesn't exist."""
    return await _links.find_one({"_id": code})


async def increment_clicks(code: str):
    """Increment the click counter for a short code (best-effort, no error raised)."""
    try:
        await _links.update_one({"_id": code}, {"$inc": {"clicks": 1}})
    except Exception as e:
        logger.warning("Failed to increment clicks for %s: %s", code, e)


async def find_existing_link(original_url: str, created_by: int):
    """
    Return an existing short link document for this URL created by this admin,
    if one already exists, to avoid generating duplicate codes for the same URL.
    """
    return await _links.find_one({"original_url": original_url, "created_by": created_by})
