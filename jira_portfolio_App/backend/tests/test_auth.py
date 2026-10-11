from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.auth import ALL_SCREENS, authenticate_token, ensure_default_admin, hash_password, issue_session, verify_password
from app.db import Base
from app.models import AppUser


def test_password_hash_round_trip() -> None:
    encoded = hash_password("A-good-local-password")
    assert encoded != "A-good-local-password"
    assert verify_password("A-good-local-password", encoded)
    assert not verify_password("wrong", encoded)


def test_default_admin_and_session_are_created_locally() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)

    admin = ensure_default_admin(db)
    assert admin.username == "admin"
    assert admin.role == "admin"
    assert admin.screen_permissions_json == ALL_SCREENS
    assert verify_password("Pass@1237", admin.password_hash)

    token, _ = issue_session(db, admin)
    authenticated = authenticate_token(db, f"Bearer {token}")
    assert authenticated.id == admin.id
    assert db.scalar(select(AppUser).where(AppUser.username == "admin")) is not None
