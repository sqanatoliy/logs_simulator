from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Literal

LogLevel = Literal["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]


@dataclass(frozen=True)
class CanonicalEvent:
    event_id: str
    ts: datetime
    level: LogLevel
    service: str
    env: str
    host: str
    region: str
    message: str
    request_id: str
    trace_id: str
    span_id: str
    user_id: str | None = None
    http_method: str | None = None
    path: str | None = None
    status_code: int | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    exception_type: str | None = None
    tags: dict[str, str] | list[str] | None = None
    raw_payload: dict[str, Any] | str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "event_id": self.event_id,
            "ts": to_rfc3339(self.ts),
            "level": self.level,
            "service": self.service,
            "env": self.env,
            "host": self.host,
            "region": self.region,
            "message": self.message,
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "user_id": self.user_id,
            "http_method": self.http_method,
            "path": self.path,
            "status_code": self.status_code,
            "latency_ms": self.latency_ms,
            "error_code": self.error_code,
            "exception_type": self.exception_type,
            "tags": self.tags,
            "raw_payload": self.raw_payload,
        }
        return data

    def with_ts(self, ts: datetime) -> "CanonicalEvent":
        return replace(self, ts=ts)


def to_rfc3339(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
