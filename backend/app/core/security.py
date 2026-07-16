from datetime import datetime, timedelta, timezone
import jwt
from pwdlib import PasswordHash
from app.core.config import settings

hasher = PasswordHash.recommended()
def hash_password(value: str) -> str: return hasher.hash(value)
def verify_password(value: str, hashed: str) -> bool: return hasher.verify(value, hashed)
def create_token(subject: str, role: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_minutes)
    return jwt.encode({"sub": subject, "role": role, "exp": exp}, settings.jwt_secret, algorithm="HS256")
def decode_token(token: str) -> dict: return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])

