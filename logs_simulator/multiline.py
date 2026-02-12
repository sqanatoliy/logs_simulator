from __future__ import annotations

from dataclasses import dataclass
from random import Random

from .models import CanonicalEvent


@dataclass(frozen=True)
class MultilineOptions:
    truncated_rate: float = 0.12


class MultilineTraceGenerator:
    def __init__(self, rng: Random, options: MultilineOptions) -> None:
        self._rng = rng
        self._options = options

    def render(self, event: CanonicalEvent, ts_text: str) -> str:
        style = self._rng.choice(("python", "java", "node"))
        lines_target = self._rng.randint(10, 30)
        caused_by = self._rng.random() < 0.6
        nested = self._rng.random() < 0.35
        truncated = self._rng.random() < self._options.truncated_rate

        if style == "python":
            lines = self._python_trace(event, ts_text, lines_target, caused_by, nested, truncated)
        elif style == "java":
            lines = self._java_trace(event, ts_text, lines_target, caused_by, nested, truncated)
        else:
            lines = self._node_trace(event, ts_text, lines_target, caused_by, nested, truncated)
        return "\n".join(lines)

    def _python_trace(
        self,
        event: CanonicalEvent,
        ts_text: str,
        lines_target: int,
        caused_by: bool,
        nested: bool,
        truncated: bool,
    ) -> list[str]:
        lines: list[str] = [
            f"{ts_text} ERROR {event.service} event_id={event.event_id} request_id={event.request_id} "
            f"trace_id={event.trace_id} Traceback (most recent call last):"
        ]

        frame_count = max(6, lines_target - 4)
        for idx in range(frame_count):
            module = self._rng.choice(("auth", "billing", "gateway", "worker", "db"))
            file_name = f"/srv/{module}/module_{idx % 9}.py"
            line_no = self._rng.randint(10, 900)
            func = self._rng.choice(("handle", "run", "process", "execute", "dispatch"))
            lines.append(f'  File "{file_name}", line {line_no}, in {func}')
            lines.append(f"    {func}(request_{idx % 4})")
            if len(lines) >= lines_target - 2:
                break

        exc = event.exception_type or self._rng.choice(("ValueError", "RuntimeError", "TimeoutError", "KeyError"))
        lines.append(f"{exc}: {event.message} [error_code={event.error_code or 'E_UNKNOWN'}]")

        if nested:
            lines.append("During handling of the above exception, another exception occurred:")
            lines.append("Traceback (most recent call last):")
            lines.append('  File "/srv/core/error_wrap.py", line 58, in wrap')
            lines.append("    raise ServiceError('wrapped failure')")
            lines.append("ServiceError: nested pipeline failure")

        if caused_by:
            lines.append("The above exception was the direct cause of the following exception:")
            lines.append("PipelineException: failed to persist event")

        if truncated:
            lines.append(f"... traceback truncated, {self._rng.randint(3, 14)} frames omitted")

        return lines

    def _java_trace(
        self,
        event: CanonicalEvent,
        ts_text: str,
        lines_target: int,
        caused_by: bool,
        nested: bool,
        truncated: bool,
    ) -> list[str]:
        root_exc = event.exception_type or self._rng.choice(
            ("java.lang.RuntimeException", "java.lang.IllegalStateException", "java.sql.SQLException")
        )
        lines: list[str] = [
            f"{ts_text} ERROR {event.service} event_id={event.event_id} request_id={event.request_id} "
            f"{root_exc}: {event.message}"
        ]

        while len(lines) < lines_target - 2:
            klass = self._rng.choice(("AuthService", "BillingProcessor", "HttpHandler", "TaskRunner", "DbProxy"))
            method = self._rng.choice(("handle", "apply", "run", "execute", "invoke"))
            file_name = f"{klass}.java"
            line_no = self._rng.randint(20, 650)
            lines.append(f"\tat com.example.{klass}.{method}({file_name}:{line_no})")
            if len(lines) >= lines_target - 2:
                break

        if caused_by:
            cause = self._rng.choice(("java.net.SocketTimeoutException", "java.io.IOException", "java.lang.NullPointerException"))
            lines.append(f"Caused by: {cause}: downstream call failed")
            for _ in range(self._rng.randint(3, 8)):
                klass = self._rng.choice(("RetryClient", "ConnectionPool", "AuthDao", "EventStore"))
                method = self._rng.choice(("send", "query", "load", "fetch"))
                line_no = self._rng.randint(10, 480)
                lines.append(f"\tat com.example.{klass}.{method}({klass}.java:{line_no})")

        if nested:
            lines.append("Suppressed: java.lang.IllegalArgumentException: invalid payload")
            lines.append("\tat com.example.Validator.validate(Validator.java:77)")

        if truncated:
            lines.append(f"\t... {self._rng.randint(2, 12)} more")

        return lines

    def _node_trace(
        self,
        event: CanonicalEvent,
        ts_text: str,
        lines_target: int,
        caused_by: bool,
        nested: bool,
        truncated: bool,
    ) -> list[str]:
        root = event.exception_type or self._rng.choice(("Error", "TypeError", "ReferenceError", "RangeError"))
        lines: list[str] = [
            f"{ts_text} ERROR {event.service} event_id={event.event_id} request_id={event.request_id} "
            f"UnhandledPromiseRejection: {root}: {event.message}"
        ]

        while len(lines) < lines_target - 2:
            fn = self._rng.choice(("processTask", "dispatch", "validateRequest", "persistRecord", "forward"))
            file_name = self._rng.choice(("app.js", "handler.js", "worker.js", "db.js", "router.js"))
            line_no = self._rng.randint(15, 450)
            col_no = self._rng.randint(2, 80)
            lines.append(f"    at {fn} (/srv/{file_name}:{line_no}:{col_no})")
            if self._rng.random() < 0.3:
                lines.append("    at processTicksAndRejections (node:internal/process/task_queues:95:5)")
            if len(lines) >= lines_target - 2:
                break

        if caused_by:
            cause = self._rng.choice(("ECONNRESET", "ETIMEDOUT", "EPIPE", "EHOSTUNREACH"))
            lines.append(f"Caused by: Error: {cause} while connecting to upstream")
            lines.append("    at Socket.onError (/srv/net.js:144:11)")

        if nested:
            lines.append("Error: nested exception while handling previous rejection")
            lines.append("    at wrapError (/srv/error.js:22:9)")

        if truncated:
            lines.append("    ... stack trace truncated ...")

        return lines
