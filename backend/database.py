"""Persistence MongoDB (via Motor, async).

Deux collections :
- ``carts``  : le DERNIER panier par utilisateur (upsert sur user_id).
- ``scans``  : l'HISTORIQUE de tous les scans (un document par scan).

Si Mongo est injoignable, les écritures sont best-effort (on log et on continue)
pour ne jamais faire planter un scan en pleine démo.
"""

from datetime import datetime, timezone
import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from config import settings
from models.schemas import ScanResponse

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def _database() -> AsyncIOMotorDatabase:
    global _client, _db
    if _db is None:
        _client = AsyncIOMotorClient(settings.mongodb_url, serverSelectionTimeoutMS=3000)
        _db = _client[settings.mongodb_db]
    return _db


async def init_db() -> None:
    """Prépare la connexion + les index. N'échoue pas si Mongo est down."""
    try:
        db = _database()
        await db["scans"].create_index([("user_id", 1), ("created_at", -1)])
        await db["carts"].create_index("user_id", unique=True)
        await db["users"].create_index("email", unique=True)
        # Ping pour vérifier la connexion tôt (logs clairs au démarrage).
        await db.command("ping")
        logger.info("MongoDB connected: %s/%s", settings.mongodb_url, settings.mongodb_db)
    except Exception as exc:
        logger.warning("MongoDB not reachable at %s (%s). Persistence disabled.",
                       settings.mongodb_url, exc)


async def save_cart(user_id: str, response: ScanResponse) -> None:
    """Upsert le dernier panier de l'utilisateur."""
    try:
        await _database()["carts"].update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id": user_id,
                "payload": response.model_dump(),
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )
    except Exception:
        logger.exception("save_cart failed for %s", user_id)


async def get_cart(user_id: str) -> ScanResponse | None:
    try:
        doc = await _database()["carts"].find_one({"user_id": user_id})
    except Exception:
        logger.exception("get_cart failed for %s", user_id)
        return None
    if not doc:
        return None
    return ScanResponse.model_validate(doc["payload"])


async def save_scan(user_id: str, response: ScanResponse) -> None:
    """Ajoute un scan à l'historique de l'utilisateur."""
    try:
        await _database()["scans"].insert_one({
            "user_id": user_id,
            "payload": response.model_dump(),
            "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        logger.exception("save_scan failed for %s", user_id)


async def create_user(email: str, password_hash: str) -> None:
    """Crée un utilisateur. Lève DuplicateKeyError si l'email existe déjà."""
    await _database()["users"].insert_one({
        "email": email,
        "password_hash": password_hash,
        "created_at": datetime.now(timezone.utc),
    })


async def get_user(email: str) -> dict | None:
    return await _database()["users"].find_one({"email": email})


async def get_history(user_id: str, limit: int = 50) -> list[ScanResponse]:
    """Renvoie les scans de l'utilisateur, du plus récent au plus ancien."""
    try:
        cursor = (
            _database()["scans"]
            .find({"user_id": user_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        return [ScanResponse.model_validate(doc["payload"]) async for doc in cursor]
    except Exception:
        logger.exception("get_history failed for %s", user_id)
        return []
