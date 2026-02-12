from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from random import Random
from typing import Any, Mapping, TypeVar

T = TypeVar("T")


def weighted_choice(rng: Random, weights: Mapping[str, float]) -> str:
    total = sum(weight for weight in weights.values() if weight > 0)
    if total <= 0:
        raise ValueError("weights total must be > 0")
    threshold = rng.random() * total
    running = 0.0
    last_key = None
    for key, weight in weights.items():
        if weight <= 0:
            continue
        running += weight
        last_key = key
        if threshold <= running:
            return key
    if last_key is None:
        raise ValueError("empty weights")
    return last_key


def deterministic_uuid(rng: Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128)))


def random_hex(rng: Random, length: int) -> str:
    alphabet = "0123456789abcdef"
    return "".join(rng.choice(alphabet) for _ in range(length))


def maybe_omit(rng: Random, value: T, probability: float) -> T | None:
    if value is None:
        return None
    if probability <= 0:
        return value
    if rng.random() < probability:
        return None
    return value


def to_rfc3339(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def ts_with_random_timezone(rng: Random, ts: datetime, probability: float) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if rng.random() >= probability:
        return to_rfc3339(ts)

    quarter_hours = rng.randint(-48, 56)
    offset = timedelta(minutes=quarter_hours * 15)
    shifted = ts.astimezone(timezone(offset))
    return shifted.isoformat(timespec="milliseconds")


def json_dumps_compact(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def quote_logfmt(value: Any) -> str:
    text = str(value)
    needs_quotes = any(ch.isspace() for ch in text) or '"' in text or "=" in text
    if not needs_quotes:
        return text
    escaped = text.replace('"', '\\"')
    return f'"{escaped}"'
