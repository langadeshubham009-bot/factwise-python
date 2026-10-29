"""Shared helpers: request parsing, validation, ids and timestamps."""
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .exceptions import NotFoundError, ValidationError


def parse(request: str) -> dict:
    try:
        data = json.loads(request)
    except (TypeError, ValueError):
        raise ValidationError("request must be a valid JSON string")
    if not isinstance(data, dict):
        raise ValidationError("request must be a JSON object")
    return data


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def require_str(data: dict, field: str, max_len: int, *, required: bool = True,
                allow_empty: bool = False) -> Optional[str]:
    """Fetch ``data[field]`` as a string, enforcing presence and max length."""
    value: Any = data.get(field)
    if value is None:
        if required:
            raise ValidationError(f"'{field}' is required")
        return None
    if not isinstance(value, str):
        raise ValidationError(f"'{field}' must be a string")
    value = value.strip()
    if not value and not allow_empty:
        raise ValidationError(f"'{field}' must not be empty")
    if len(value) > max_len:
        raise ValidationError(f"'{field}' can be at most {max_len} characters")
    return value


def check_timestamp(value: Optional[str], field: str) -> str:
    """Accept a client supplied ISO-8601 timestamp, defaulting to now."""
    if value is None:
        return now()
    try:
        datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError(f"'{field}' must be an ISO-8601 date:time string")
    return value


def require_found(record: Optional[dict], kind: str, key: Any) -> dict:
    if record is None:
        raise NotFoundError(f"{kind} '{key}' not found")
    return record


def dumps(obj: Any) -> str:
    return json.dumps(obj)
