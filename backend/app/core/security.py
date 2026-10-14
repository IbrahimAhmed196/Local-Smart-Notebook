"""Security helpers: passwords, JWT tokens, safe file names and paths."""
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.core.config import settings
from app.core.exceptions import InvalidFileError

_password_hash = PasswordHash.recommended()  # Argon2


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _password_hash.verify(password, hashed)
    except UnknownHashError:  # e.g. a placeholder value like "fakepassword"
        return False


# Burns the same CPU time when an e-mail does not exist (see auth_service.login)
DUMMY_HASH = hash_password("not-a-real-password")


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": str(user_id), "exp": expire}  # the JWT standard wants a string
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    """Return the user id stored in the token, or None if invalid/expired."""
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


# ---- Safe file names and paths (used by document uploads) ----
_UNSAFE = re.compile(r"[^\w\s.\-()\[\]]", re.UNICODE)   # \w keeps Arabic letters
MAX_NAME_LEN = 150


def sanitize_filename(raw: str) -> str:
    name = unicodedata.normalize("NFKC", raw or "")
    name = name.replace("\\", "/").split("/")[-1]
    name = "".join(c for c in name if c.isprintable())
    name = _UNSAFE.sub("_", name).strip(" .")
    if not name:
        raise InvalidFileError("Missing or invalid filename.")
    stem, dot, ext = name.rpartition(".")
    if not dot:
        return name[:MAX_NAME_LEN]
    return f"{stem[: MAX_NAME_LEN - len(ext) - 1]}.{ext}"


def safe_join(base: Path, relative: str) -> Path:
    base = base.resolve()
    target = (base / relative).resolve()
    if base != target and base not in target.parents:
        raise InvalidFileError("Invalid storage path.")
    return target
