"""Auth helpers : hashing bcrypt + jetons JWT.

Le `sub` du JWT est l'email de l'utilisateur, qui sert d'``user_id`` partout
(panier + historique sont indexés dessus).
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config import settings

_ALGO = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_token(email: str) -> str:
    payload = {
        "sub": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO)


def decode_token(token: str) -> str | None:
    """Renvoie l'email (sub) si le token est valide, sinon None."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGO])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
