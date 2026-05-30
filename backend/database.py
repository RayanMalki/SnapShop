import json
from pathlib import Path

import aiosqlite

from config import settings
from models.schemas import ScanResponse

DB_PATH = Path(settings.database_url.replace("sqlite:///", ""))


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS carts (
                user_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.commit()


async def save_cart(user_id: str, response: ScanResponse) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO carts (user_id, payload, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                payload = excluded.payload,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, response.model_dump_json()),
        )
        await db.commit()


async def get_cart(user_id: str) -> ScanResponse | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT payload FROM carts WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return ScanResponse.model_validate_json(row[0])
