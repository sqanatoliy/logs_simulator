from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from random import Random
from typing import Any, Protocol

from .config import NoiseConfig, SimulatorConfig
from .models import CanonicalEvent
from .multiline import MultilineOptions, MultilineTraceGenerator
from .utils import maybe_omit, quote_logfmt, to_rfc3339, ts_with_random_timezone


CSV_FIELDS = [
    "event_id",
    "ts",
    "level",
    "service",
    "env",
    "host",
    "region",
    "message",
    "request_id",
    "trace_id",
    "span_id",
    "user_id",
    "http_method",
    "path",
    "status_code",
    "latency_ms",
    "error_code",
    "exception_type",
    "tags",
    "raw_payload",
]


@dataclass(frozen=True)
class FormatterContext:
    rng: Random
    config: SimulatorConfig
    noise: NoiseConfig


class Formatter(Protocol):
    name: str
    extension: str

    def render(self, event: CanonicalEvent, ctx: FormatterContext) -> str:
        ...

    def header(self) -> str | None:
        return None


class JsonlFormatter:
    name = "jsonl"
    extension = "jsonl"

    def render(self, event: CanonicalEvent, ctx: FormatterContext) -> str:
        payload = event.to_dict()
        _drop_optional_keys(payload, ctx.rng, ctx.noise.missing_field_rate)
        if ctx.config.include_loki_labels:
            payload["loki_labels"] = {
                "service": event.service,
                "env": event.env,
                "level": event.level,
                "region": event.region,
            }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


class CsvFormatter:
    name = "csv"
    extension = "csv"

    def header(self) -> str:
        return ",".join(CSV_FIELDS)

    def render(self, event: CanonicalEvent, ctx: FormatterContext) -> str:
        payload = event.to_dict()
        _drop_optional_keys(payload, ctx.rng, ctx.noise.missing_field_rate)
        row = [payload.get(field) for field in CSV_FIELDS]
        normalized: list[str] = []
        for item in row:
            if item is None:
                normalized.append("")
            elif isinstance(item, (dict, list)):
                normalized.append(json.dumps(item, separators=(",", ":"), ensure_ascii=False))
            else:
                normalized.append(str(item))

        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(normalized)
        return buffer.getvalue().strip("\r\n")


class PlainFormatter:
    name = "plain"
    extension = "log"

    def render(self, event: CanonicalEvent, ctx: FormatterContext) -> str:
        ts_text = ts_with_random_timezone(ctx.rng, event.ts, ctx.noise.timezone_variation_rate)
        status = maybe_omit(ctx.rng, event.status_code, ctx.noise.missing_field_rate)
        latency = maybe_omit(ctx.rng, event.latency_ms, ctx.noise.missing_field_rate)
        path = maybe_omit(ctx.rng, event.path, ctx.noise.missing_field_rate)
        method = maybe_omit(ctx.rng, event.http_method, ctx.noise.missing_field_rate)
        user_id = maybe_omit(ctx.rng, event.user_id, ctx.noise.missing_field_rate)
        fields = [
            f"{ts_text}",
            event.level,
            event.service,
            f"event_id={event.event_id}",
            f"request_id={event.request_id}",
            f"trace_id={event.trace_id}",
            f"span_id={event.span_id}",
            f"env={event.env}",
            f"region={event.region}",
        ]
        if method:
            fields.append(f"method={method}")
        if path:
            fields.append(f"path={path}")
        if status is not None:
            fields.append(f"status={status}")
        if latency is not None:
            fields.append(f"latency_ms={latency}")
        if user_id:
            fields.append(f"user_id={user_id}")
        if event.error_code and ctx.rng.random() > ctx.noise.missing_field_rate:
            fields.append(f"error_code={event.error_code}")
        fields.append(f"message={json.dumps(event.message, ensure_ascii=False)}")
        return " ".join(fields)


class LogfmtFormatter:
    name = "logfmt"
    extension = "logfmt"

    def render(self, event: CanonicalEvent, ctx: FormatterContext) -> str:
        ts_text = ts_with_random_timezone(ctx.rng, event.ts, ctx.noise.timezone_variation_rate)
        payload: dict[str, Any] = {
            "ts": ts_text,
            "level": event.level,
            "service": event.service,
            "event_id": event.event_id,
            "request_id": event.request_id,
            "trace_id": event.trace_id,
            "span_id": event.span_id,
            "env": event.env,
            "host": event.host,
            "region": event.region,
            "message": event.message,
        }
        optional = {
            "user_id": event.user_id,
            "method": event.http_method,
            "path": event.path,
            "status": event.status_code,
            "latency_ms": event.latency_ms,
            "error_code": event.error_code,
            "exception_type": event.exception_type,
        }
        for key, value in optional.items():
            payload[key] = maybe_omit(ctx.rng, value, ctx.noise.missing_field_rate)

        if ctx.config.include_loki_labels:
            payload["loki_service"] = event.service
            payload["loki_env"] = event.env
            payload["loki_region"] = event.region

        parts: list[str] = []
        for key, value in payload.items():
            if value is None:
                continue
            parts.append(f"{key}={quote_logfmt(value)}")
        return " ".join(parts)


class SyslogFormatter:
    name = "syslog"
    extension = "syslog"

    def render(self, event: CanonicalEvent, ctx: FormatterContext) -> str:
        severity_map = {"DEBUG": 7, "INFO": 6, "WARN": 4, "ERROR": 3, "FATAL": 2}
        facility = 20
        pri = facility * 8 + severity_map.get(event.level, 5)
        ts_text = ts_with_random_timezone(ctx.rng, event.ts, ctx.noise.timezone_variation_rate)
        procid = "-"
        msgid = event.event_id

        meta: dict[str, Any] = {
            "request_id": event.request_id,
            "trace_id": event.trace_id,
            "span_id": event.span_id,
            "env": event.env,
            "region": event.region,
            "status": maybe_omit(ctx.rng, event.status_code, ctx.noise.missing_field_rate),
            "latency_ms": maybe_omit(ctx.rng, event.latency_ms, ctx.noise.missing_field_rate),
        }

        kv_pairs = " ".join(f"{key}=\"{value}\"" for key, value in meta.items() if value is not None)
        structured = f"[meta {kv_pairs}]" if kv_pairs else "-"
        message = event.message.replace("\n", " ")

        return f"<{pri}>1 {ts_text} {event.host} {event.service} {procid} {msgid} {structured} {message}"


class AccessFormatter:
    name = "access"
    extension = "access.log"

    def render(self, event: CanonicalEvent, ctx: FormatterContext) -> str:
        ts = event.ts
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ctx.rng.random() < ctx.noise.timezone_variation_rate:
            ts_text = ts_with_random_timezone(ctx.rng, ts, 1.0)
            dt = _parse_iso(ts_text)
        else:
            dt = ts.astimezone(timezone.utc)

        apache_ts = dt.strftime("%d/%b/%Y:%H:%M:%S %z")
        method = event.http_method or ctx.rng.choice(("GET", "POST", "PUT", "DELETE"))
        path = event.path or "/healthz"
        status = event.status_code if event.status_code is not None else 200
        bytes_sent = ctx.rng.randint(120, 12_000)
        latency = maybe_omit(ctx.rng, event.latency_ms, ctx.noise.missing_field_rate)
        user = event.user_id or "-"
        ua = ctx.rng.choice(
            (
                "Mozilla/5.0",
                "curl/8.4.0",
                "python-requests/2.32",
                "Go-http-client/1.1",
            )
        )
        ref = ctx.rng.choice(("-", "https://example.com", "https://grafana.local/d/ops"))
        extra_parts = [
            f"event_id={event.event_id}",
            f"trace_id={event.trace_id}",
            f"service={event.service}",
            f"env={event.env}",
        ]
        if latency is not None:
            extra_parts.append(f"latency_ms={latency}")

        return (
            f"{event.host} - {user} [{apache_ts}] \"{method} {path} HTTP/1.1\" {status} {bytes_sent} "
            f"\"{ref}\" \"{ua}\" {' '.join(extra_parts)}"
        )


class MultilineFormatter:
    name = "multiline"
    extension = "log"

    def __init__(self, rng: Random, noise: NoiseConfig) -> None:
        self._generator = MultilineTraceGenerator(rng=rng, options=MultilineOptions(truncated_rate=noise.truncated_multiline_rate))

    def render(self, event: CanonicalEvent, ctx: FormatterContext) -> str:
        ts_text = ts_with_random_timezone(ctx.rng, event.ts, ctx.noise.timezone_variation_rate)
        return self._generator.render(event, ts_text)


class MixedFormatter:
    name = "mixed"
    extension = "log"

    def __init__(self, jsonl: JsonlFormatter, plain: PlainFormatter, logfmt: LogfmtFormatter) -> None:
        self._jsonl = jsonl
        self._plain = plain
        self._logfmt = logfmt

    def render(self, event: CanonicalEvent, ctx: FormatterContext) -> str:
        mode_roll = ctx.rng.random()
        if mode_roll < ctx.noise.mixed_json_rate:
            return self._jsonl.render(event, ctx)
        if mode_roll < 0.5 + (1.0 - ctx.noise.mixed_json_rate) / 2:
            return self._plain.render(event, ctx)
        return self._logfmt.render(event, ctx)


class FormatterRegistry:
    def __init__(self, rng: Random, noise: NoiseConfig) -> None:
        jsonl = JsonlFormatter()
        plain = PlainFormatter()
        logfmt = LogfmtFormatter()
        self._formatters: dict[str, Formatter] = {
            "jsonl": jsonl,
            "csv": CsvFormatter(),
            "plain": plain,
            "logfmt": logfmt,
            "syslog": SyslogFormatter(),
            "access": AccessFormatter(),
            "multiline": MultilineFormatter(rng, noise),
            "mixed": MixedFormatter(jsonl, plain, logfmt),
        }

    def get(self, name: str) -> Formatter:
        try:
            return self._formatters[name]
        except KeyError as exc:
            raise ValueError(f"unknown formatter: {name}") from exc


def _drop_optional_keys(payload: dict[str, Any], rng: Random, probability: float) -> None:
    optional_keys = (
        "user_id",
        "http_method",
        "path",
        "status_code",
        "latency_ms",
        "error_code",
        "exception_type",
        "tags",
        "raw_payload",
    )
    for key in optional_keys:
        if key in payload and payload[key] is not None and rng.random() < probability:
            payload.pop(key)


def _parse_iso(ts_text: str):
    if ts_text.endswith("Z"):
        ts_text = ts_text.replace("Z", "+00:00")
    return datetime.fromisoformat(ts_text)
