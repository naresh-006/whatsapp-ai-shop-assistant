"""MongoDB database connection layer with graceful in-memory development fallback."""

import logging
from typing import Any
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from pymongo.database import Database
from pymongo.collection import Collection

from app.config import settings

logger = logging.getLogger(__name__)

# Global client and db references
_client: Any = None
_db: Any = None
_is_mock: bool = False


def init_db() -> tuple[bool, str | None]:
    """
    Attempt connection to live MongoDB.
    If unreachable, gracefully fall back to in-memory mongomock for interactive demo mode.
    """
    global _client, _db, _is_mock

    # 1. Try Live MongoDB
    try:
        live_client = MongoClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=1500,
            connectTimeoutMS=1500,
        )
        live_client.admin.command("ping")
        _client = live_client
        _db = live_client[settings.MONGODB_DB_NAME]
        _is_mock = False
        logger.info("Successfully connected to live MongoDB: %s", settings.MONGODB_URI)
        return True, None
    except Exception as exc:
        # 2. Fall back to in-memory mongomock for local development
        import mongomock
        logger.warning(
            "Live MongoDB at %s is offline (%s). Using In-Memory Database for local testing.",
            settings.MONGODB_URI,
            exc,
        )
        _client = mongomock.MongoClient()
        _db = _client[settings.MONGODB_DB_NAME]
        _is_mock = True

        # Pre-seed real family products so interactive API testing works immediately out of the box
        try:
            from app.services.product_service import seed_real_products
            seed_real_products()
            logger.info("Pre-seeded 12 verified family products into in-memory catalog.")
        except Exception as seed_err:
            logger.debug("Could not auto-seed real products: %s", seed_err)

        return False, str(exc)


def get_mongo_client() -> Any:
    """Return or initialize the singleton MongoDB client."""
    global _client
    if _client is None:
        init_db()
    return _client


def get_database() -> Database:
    """Return the application database handle."""
    global _db
    if _db is None:
        init_db()
    return _db


def close_mongo_connection() -> None:
    """Close the MongoDB client connection cleanly."""
    global _client, _db, _is_mock
    if _client is not None and not _is_mock:
        logger.info("Closing MongoDB connection.")
        try:
            _client.close()
        except Exception:
            pass
    _client = None
    _db = None
    _is_mock = False


def check_db_connection() -> dict[str, Any]:
    """
    Ping MongoDB to verify active connectivity.
    Returns status dictionary indicating connectivity and mode.
    """
    global _client, _is_mock
    if _client is None:
        init_db()

    if _is_mock:
        return {
            "connected": False,
            "mode": "in-memory-demo",
            "database": settings.MONGODB_DB_NAME,
            "error": "MongoDB server offline. Running in In-Memory Demo Mode with pre-seeded products.",
        }

    try:
        _client.admin.command("ping")
        return {
            "connected": True,
            "mode": "live-mongodb",
            "database": settings.MONGODB_DB_NAME,
            "error": None,
        }
    except Exception as exc:
        return {
            "connected": False,
            "mode": "unreachable",
            "database": settings.MONGODB_DB_NAME,
            "error": str(exc),
        }


# Authoritative Collection Accessors
def get_products_collection() -> Collection:
    """Return products collection."""
    return get_database()["products"]


def get_sales_collection() -> Collection:
    """Return sales collection."""
    return get_database()["sales"]


def get_users_collection() -> Collection:
    """Return users collection."""
    return get_database()["users"]


def get_audit_logs_collection() -> Collection:
    """Return audit logs collection."""
    return get_database()["audit_logs"]


if __name__ == "__main__":
    print(f"Testing MongoDB connection to {settings.MONGODB_URI}...")
    status = check_db_connection()
    print("Database Status:", status)
