import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppSession, AppUser

ALL_SCREENS = ["overview", "hierarchy", "traceability", "wbs", "sprints", "intelligence", "documentation"]
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "Pass@1237"


def hash_password(password: str, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), actual_salt, 310_000)
    return f"pbkdf2_sha256$310000${actual_salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


def ensure_default_admin(db: Session) -> AppUser:
    user = db.scalar(select(AppUser).where(AppUser.username == DEFAULT_ADMIN_USERNAME))
    if user is None:
        user = AppUser(
            username=DEFAULT_ADMIN_USERNAME,
            display_name="Administrator",
            password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
            role="admin",
            screen_permissions_json=ALL_SCREENS,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def issue_session(db: Session, user: AppUser) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(40)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=12)
    db.add(AppSession(user_id=user.id, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=expires_at))
    db.commit()
    return token, expires_at


def authenticate_token(db: Session, authorization: str | None) -> AppUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
    session = db.scalar(select(AppSession).where(AppSession.token_hash == token_hash))
    now = datetime.now(timezone.utc)
    if session is None or session.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    user = db.get(AppUser, session.user_id)
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="User is inactive")
    return user


def public_user(user: AppUser) -> dict[str, object]:
    permissions = ALL_SCREENS if user.role == "admin" else list(user.screen_permissions_json or [])
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "screen_permissions": permissions,
        "active": user.active,
    }
