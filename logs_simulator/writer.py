from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

from .models import to_rfc3339


@dataclass
class FileState:
    path: Path
    handle: IO[str]
    opened_at: datetime
    bytes_written: int
    index: int
    header_written: bool


class RotatingFileRouter:
    def __init__(self, out_dir: Path, max_bytes: int, interval_sec: int, use_gzip: bool) -> None:
        self._out_dir = out_dir
        self._max_bytes = max_bytes
        self._interval_sec = interval_sec
        self._use_gzip = use_gzip
        self._states: dict[tuple[str, str, str], FileState] = {}

    def write(
        self,
        service: str,
        format_name: str,
        extension: str,
        ts: datetime,
        payload: str,
        header: str | None = None,
    ) -> Path:
        date_key, date_path = _date_parts(ts)
        key = (service, format_name, date_key)
        state = self._states.get(key)

        if state is None:
            state = self._open_new_file(service, format_name, extension, ts, index=0, date_path=date_path)
            self._states[key] = state

        encoded_len = len((payload + "\n").encode("utf-8"))
        if self._should_rotate(state, ts, encoded_len):
            self._close_state(state)
            state = self._open_new_file(service, format_name, extension, ts, index=state.index + 1, date_path=date_path)
            self._states[key] = state

        if header and not state.header_written:
            state.handle.write(header + "\n")
            state.bytes_written += len((header + "\n").encode("utf-8"))
            state.header_written = True

        state.handle.write(payload + "\n")
        state.bytes_written += encoded_len
        return state.path

    def close(self) -> None:
        for state in self._states.values():
            self._close_state(state)
        self._states.clear()

    def _should_rotate(self, state: FileState, ts: datetime, incoming_bytes: int) -> bool:
        time_delta = ts - state.opened_at
        if time_delta.total_seconds() >= self._interval_sec:
            return True
        return (state.bytes_written + incoming_bytes) >= self._max_bytes

    def _open_new_file(
        self,
        service: str,
        format_name: str,
        extension: str,
        ts: datetime,
        index: int,
        date_path: Path,
    ) -> FileState:
        service_dir = self._out_dir / date_path / service / format_name
        service_dir.mkdir(parents=True, exist_ok=True)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        stamp = ts.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base_name = f"{service}_{format_name}_{stamp}_{index:04d}.{extension}"
        file_path = service_dir / (base_name + (".gz" if self._use_gzip else ""))

        if self._use_gzip:
            handle = gzip.open(file_path, mode="at", encoding="utf-8")
        else:
            handle = file_path.open("a", encoding="utf-8")

        return FileState(
            path=file_path,
            handle=handle,
            opened_at=ts,
            bytes_written=0,
            index=index,
            header_written=False,
        )

    @staticmethod
    def _close_state(state: FileState) -> None:
        state.handle.flush()
        state.handle.close()


class GroundTruthWriter:
    def __init__(self, out_dir: Path, use_gzip: bool = False) -> None:
        self._out_dir = out_dir
        self._use_gzip = use_gzip
        self._handles: dict[str, IO[str]] = {}
        self._paths: dict[str, Path] = {}

    def write(self, event_payload: dict[str, object], ts: datetime) -> Path:
        date_key, date_path = _date_parts(ts)
        handle = self._handles.get(date_key)

        if handle is None:
            gt_dir = self._out_dir / date_path / "ground_truth"
            gt_dir.mkdir(parents=True, exist_ok=True)
            file_name = "ground_truth.jsonl" + (".gz" if self._use_gzip else "")
            file_path = gt_dir / file_name
            if self._use_gzip:
                handle = gzip.open(file_path, mode="at", encoding="utf-8")
            else:
                handle = file_path.open("a", encoding="utf-8")
            self._handles[date_key] = handle
            self._paths[date_key] = file_path

        handle.write(json.dumps(event_payload, separators=(",", ":"), ensure_ascii=False) + "\n")
        return self._paths[date_key]

    def close(self) -> None:
        for handle in self._handles.values():
            handle.flush()
            handle.close()
        self._handles.clear()
        self._paths.clear()


def malformed_line(event_id: str, rng_seed_fragment: int, ts: datetime) -> str:
    variants = [
        f"{{\"ts\":\"BROKEN\",\"event_id\":\"{event_id}\",\"message\":\"unterminated",
        f"event_id={event_id} level==ERROR msg=\"bad line without closing quote",
        f"<13>1 ??? host svc - {event_id} [meta key=\"x\"] MALFORMED\x00LINE_{rng_seed_fragment}",
        f"{to_rfc3339(ts)} ??? event_id={event_id} status=two_hundred",
    ]
    return variants[rng_seed_fragment % len(variants)]


def _date_parts(ts: datetime) -> tuple[str, Path]:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts = ts.astimezone(timezone.utc)
    key = ts.strftime("%Y-%m-%d")
    path = Path(ts.strftime("%Y/%m/%d"))
    return key, path
