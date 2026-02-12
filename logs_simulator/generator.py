from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from random import Random
from typing import Any

from .config import IncidentConfig, NoiseConfig, SimulatorConfig
from .formatters import FormatterContext, FormatterRegistry
from .models import CanonicalEvent
from .utils import deterministic_uuid, random_hex, weighted_choice
from .writer import GroundTruthWriter, RotatingFileRouter, malformed_line


@dataclass
class GenerationStats:
    total_events: int = 0
    duplicates: int = 0
    malformed_lines: int = 0
    by_format: dict[str, int] = field(default_factory=dict)
    output_files: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class IncidentEffect:
    error_rate_multiplier: float = 1.0
    latency_multiplier: float = 1.0
    five_xx_boost: float = 0.0


class EventFactory:
    def __init__(self, config: SimulatorConfig, rng: Random, noise: NoiseConfig, start_time: datetime) -> None:
        self._config = config
        self._rng = rng
        self._noise = noise
        self._start = start_time.astimezone(timezone.utc)

        self._services = {service.name: service.weight for service in config.services}
        self._envs = config.envs
        self._regions = config.regions
        self._levels = config.level_distribution
        self._methods = config.http_methods
        self._paths = config.paths

        self._base_latency = {
            service.name: self._rng.randint(15, 180) for service in config.services
        }

        self._hosts: dict[str, list[str]] = {}
        for service in self._services:
            self._hosts[service] = [f"{service}-{idx:02d}.node.local" for idx in range(1, self._rng.randint(8, 16))]

    def build(self, second_offset: int) -> CanonicalEvent:
        service = weighted_choice(self._rng, self._services)
        incident = self._incident_effect(second_offset, service)

        ts = self._start + timedelta(seconds=second_offset, milliseconds=self._rng.randint(0, 999))
        if self._noise.out_of_order_max_sec > 0 and self._rng.random() < self._noise.out_of_order_rate:
            ts -= timedelta(
                seconds=self._rng.randint(1, self._noise.out_of_order_max_sec),
                milliseconds=self._rng.randint(0, 999),
            )

        env = weighted_choice(self._rng, self._envs)
        region = weighted_choice(self._rng, self._regions)
        host = self._rng.choice(self._hosts[service])

        level = self._choose_level(incident)

        has_http = self._rng.random() < 0.82
        method = weighted_choice(self._rng, self._methods) if has_http else None
        path = self._rng.choice(self._paths) if has_http else None

        latency = self._choose_latency(service, incident, level)
        status = self._choose_status(level, incident, latency, has_http)

        error_code = None
        exc_type = None
        if level in ("ERROR", "FATAL") or (status is not None and status >= 500):
            error_code = self._rng.choice(("AUTH_401", "DB_TIMEOUT", "UPSTREAM_502", "RATE_LIMIT", "PAYMENT_DECLINED"))
            exc_type = self._rng.choice(
                (
                    "TimeoutError",
                    "ConnectionError",
                    "ValidationError",
                    "RuntimeError",
                    "SQLException",
                    "NullPointerException",
                )
            )

        if status is not None and status >= 500 and level not in ("ERROR", "FATAL"):
            level = "ERROR"

        message = self._build_message(level, service, method, path, status, latency, error_code)

        tags = self._build_tags(service, env)
        raw_payload = None
        if self._rng.random() < 0.14:
            raw_payload = {
                "attempt": self._rng.randint(1, 5),
                "client": self._rng.choice(("web", "mobile", "partner-api", "internal-job")),
                "feature_flag": self._rng.choice(("checkout_v2", "new-auth", "edge-cache", "-")),
            }

        user_id = None
        if self._rng.random() < 0.65:
            user_id = f"usr_{self._rng.randint(10_000, 999_999)}"

        return CanonicalEvent(
            event_id=deterministic_uuid(self._rng),
            ts=ts,
            level=level,
            service=service,
            env=env,
            host=host,
            region=region,
            message=message,
            request_id=f"req_{random_hex(self._rng, 12)}",
            trace_id=random_hex(self._rng, 32),
            span_id=random_hex(self._rng, 16),
            user_id=user_id,
            http_method=method,
            path=path,
            status_code=status,
            latency_ms=latency,
            error_code=error_code,
            exception_type=exc_type,
            tags=tags,
            raw_payload=raw_payload,
        )

    def _choose_level(self, incident: IncidentEffect) -> str:
        weights = dict(self._levels)
        if incident.error_rate_multiplier > 1:
            weights["ERROR"] = weights.get("ERROR", 0.0) * incident.error_rate_multiplier
            weights["FATAL"] = weights.get("FATAL", 0.0) * (1 + (incident.error_rate_multiplier - 1) * 0.6)
            weights["INFO"] = max(0.001, weights.get("INFO", 0.0) / (1 + (incident.error_rate_multiplier - 1) * 0.8))
            weights["DEBUG"] = max(0.001, weights.get("DEBUG", 0.0) / incident.error_rate_multiplier)
        return weighted_choice(self._rng, weights)

    def _choose_latency(self, service: str, incident: IncidentEffect, level: str) -> int:
        base = float(self._base_latency[service])
        if level == "WARN":
            base *= 1.4
        elif level in ("ERROR", "FATAL"):
            base *= 2.0
        base *= incident.latency_multiplier
        sample = int(max(1, self._rng.gauss(base, max(3.0, base * 0.35))))
        return min(sample, 30_000)

    def _choose_status(self, level: str, incident: IncidentEffect, latency: int, has_http: bool) -> int | None:
        if not has_http:
            return None

        p_5xx = 0.02 + incident.five_xx_boost
        p_4xx = 0.08
        if level in ("ERROR", "FATAL"):
            p_5xx += 0.43
            p_4xx += 0.12
        if latency > 600:
            p_5xx += min(0.33, latency / 4000)

        roll = self._rng.random()
        if roll < p_5xx:
            return self._rng.choice((500, 500, 502, 503, 504))
        if roll < (p_5xx + p_4xx):
            return self._rng.choice((400, 401, 403, 404, 409, 429))
        if roll < (p_5xx + p_4xx + 0.08):
            return self._rng.choice((301, 302, 304))
        return self._rng.choice((200, 200, 200, 201, 202, 204))

    def _build_message(
        self,
        level: str,
        service: str,
        method: str | None,
        path: str | None,
        status: int | None,
        latency: int,
        error_code: str | None,
    ) -> str:
        if method and path and status is not None:
            if level in ("ERROR", "FATAL"):
                return (
                    f"request failed service={service} method={method} path={path} "
                    f"status={status} latency_ms={latency} code={error_code or 'UNKNOWN'}"
                )
            if level == "WARN":
                return f"request completed with warning method={method} path={path} status={status} latency_ms={latency}"
            return f"request completed method={method} path={path} status={status} latency_ms={latency}"

        if level in ("ERROR", "FATAL"):
            return f"background job failed in {service} code={error_code or 'UNKNOWN'} latency_ms={latency}"
        if level == "WARN":
            return f"background job degraded in {service} latency_ms={latency}"
        return f"background job completed in {service} latency_ms={latency}"

    def _build_tags(self, service: str, env: str) -> dict[str, str] | list[str]:
        tags: dict[str, str] = {
            "service": service,
            "env": env,
        }
        for key, values in self._config.tags_pool.items():
            if values and self._rng.random() < 0.9:
                tags[key] = self._rng.choice(values)

        if self._rng.random() < 0.25:
            return [f"{k}:{v}" for k, v in tags.items()]
        return tags

    def _incident_effect(self, second_offset: int, service: str) -> IncidentEffect:
        effect = IncidentEffect()
        for incident in self._config.incidents:
            if not _incident_active(incident, second_offset):
                continue
            if incident.affected_services and service not in incident.affected_services:
                continue
            effect = IncidentEffect(
                error_rate_multiplier=effect.error_rate_multiplier * incident.error_rate_multiplier,
                latency_multiplier=effect.latency_multiplier * incident.latency_multiplier,
                five_xx_boost=min(0.95, effect.five_xx_boost + incident.five_xx_boost),
            )
        return effect


class SimulationEngine:
    def __init__(
        self,
        config: SimulatorConfig,
        out_dir: Path,
        duration_sec: int,
        events_per_sec: int,
        seed: int,
        challenge_mode: bool,
        use_gzip: bool,
    ) -> None:
        self._config = config
        self._duration_sec = duration_sec
        self._events_per_sec = events_per_sec
        self._rng = Random(seed)
        self._noise = config.effective_noise(challenge_mode)

        start_time = config.start_time or datetime.now(tz=timezone.utc).replace(microsecond=0)
        self._event_factory = EventFactory(config=config, rng=self._rng, noise=self._noise, start_time=start_time)

        self._router = RotatingFileRouter(
            out_dir=out_dir,
            max_bytes=config.rotation.max_bytes,
            interval_sec=config.rotation.interval_sec,
            use_gzip=use_gzip,
        )
        self._ground_truth = GroundTruthWriter(out_dir=out_dir, use_gzip=use_gzip)

        self._ctx = FormatterContext(rng=self._rng, config=config, noise=self._noise)
        self._formatters = FormatterRegistry(rng=self._rng, noise=self._noise)

        self._format_dist = config.normalized_distribution(config.format_distribution)

        self._active_spike_until = -1
        self._active_spike_mul = 1.0

    def generate(self) -> GenerationStats:
        stats = GenerationStats()
        for second_offset in range(self._duration_sec):
            self._generate_second(second_offset, stats)
        self.close()
        return stats

    def stream(self, duration_sec: int | None = None) -> GenerationStats:
        stats = GenerationStats()
        second_offset = 0

        try:
            while True:
                loop_start = time.time()
                self._generate_second(second_offset, stats)
                second_offset += 1

                if duration_sec is not None and second_offset >= duration_sec:
                    break

                elapsed = time.time() - loop_start
                if elapsed < 1.0:
                    time.sleep(1.0 - elapsed)
        except KeyboardInterrupt:
            pass
        finally:
            self.close()

        return stats

    def close(self) -> None:
        self._router.close()
        self._ground_truth.close()

    def _generate_second(self, second_offset: int, stats: GenerationStats) -> None:
        count = self._events_for_second(second_offset)
        events: list[CanonicalEvent] = []
        for _ in range(count):
            event = self._event_factory.build(second_offset)
            events.append(event)
            if self._rng.random() < self._noise.duplicate_rate:
                stats.duplicates += 1
                events.append(event)

        self._rng.shuffle(events)

        for event in events:
            format_name = weighted_choice(self._rng, self._format_dist)
            formatter = self._formatters.get(format_name)
            payload = formatter.render(event, self._ctx)
            header = formatter.header() if hasattr(formatter, "header") else None
            path = self._router.write(
                service=event.service,
                format_name=format_name,
                extension=formatter.extension,
                ts=event.ts,
                payload=payload,
                header=header,
            )
            stats.output_files.add(str(path))
            stats.by_format[format_name] = stats.by_format.get(format_name, 0) + 1
            stats.total_events += 1

            gt_payload = event.to_dict()
            gt_payload["raw_format"] = format_name
            gt_payload["raw_file"] = str(path)
            self._ground_truth.write(gt_payload, event.ts)

            if self._rng.random() < self._noise.malformed_rate:
                bad_line = malformed_line(event.event_id, self._rng.randint(1, 100_000), event.ts)
                self._router.write(
                    service=event.service,
                    format_name=format_name,
                    extension=formatter.extension,
                    ts=event.ts,
                    payload=bad_line,
                    header=None,
                )
                stats.malformed_lines += 1

    def _events_for_second(self, second_offset: int) -> int:
        multiplier = self._intensity_multiplier(second_offset)
        load = self._events_per_sec * multiplier
        sampled = int(max(0, self._rng.gauss(load, max(1.0, load * 0.12))))
        return sampled

    def _intensity_multiplier(self, second_offset: int) -> float:
        multiplier = 1.0
        for window in self._config.intensity_profile:
            if window.start_sec <= second_offset < window.end_sec:
                multiplier *= window.multiplier

        if second_offset > self._active_spike_until:
            spike_prob = self._config.spikes.probability_per_minute / 60.0
            if self._rng.random() < spike_prob:
                duration = self._rng.randint(
                    self._config.spikes.min_duration_sec,
                    self._config.spikes.max_duration_sec,
                )
                self._active_spike_until = second_offset + duration
                self._active_spike_mul = self._rng.uniform(
                    self._config.spikes.min_multiplier,
                    self._config.spikes.max_multiplier,
                )

        if second_offset <= self._active_spike_until:
            multiplier *= self._active_spike_mul

        return max(0.1, multiplier)


def _incident_active(incident: IncidentConfig, second_offset: int) -> bool:
    return incident.start_sec <= second_offset < (incident.start_sec + incident.duration_sec)
