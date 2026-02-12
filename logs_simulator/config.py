from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


SUPPORTED_FORMATS = (
    "jsonl",
    "csv",
    "plain",
    "logfmt",
    "syslog",
    "access",
    "multiline",
    "mixed",
)


class ServiceConfig(BaseModel):
    name: str
    weight: float = 1.0

    @field_validator("weight")
    @classmethod
    def _weight_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("service weight must be > 0")
        return value


class IntensityWindow(BaseModel):
    start_sec: int = 0
    end_sec: int
    multiplier: float = 1.0

    @field_validator("end_sec")
    @classmethod
    def _end_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("end_sec must be > 0")
        return value

    @field_validator("multiplier")
    @classmethod
    def _mul_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("multiplier must be > 0")
        return value


class IncidentConfig(BaseModel):
    start_sec: int
    duration_sec: int
    affected_services: list[str] = Field(default_factory=list)
    error_rate_multiplier: float = 3.0
    latency_multiplier: float = 2.0
    five_xx_boost: float = 0.25

    @field_validator("duration_sec")
    @classmethod
    def _duration_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("duration_sec must be > 0")
        return value

    @field_validator("error_rate_multiplier", "latency_multiplier")
    @classmethod
    def _mult_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("incident multipliers must be > 0")
        return value


class NoiseConfig(BaseModel):
    duplicate_rate: float = 0.01
    out_of_order_rate: float = 0.02
    out_of_order_max_sec: int = 8
    missing_field_rate: float = 0.07
    malformed_rate: float = 0.01
    timezone_variation_rate: float = 0.05
    truncated_multiline_rate: float = 0.12
    mixed_json_rate: float = 0.45

    @field_validator(
        "duplicate_rate",
        "out_of_order_rate",
        "missing_field_rate",
        "malformed_rate",
        "timezone_variation_rate",
        "truncated_multiline_rate",
        "mixed_json_rate",
    )
    @classmethod
    def _rate_range(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("rates must be in [0, 1]")
        return value

    @field_validator("out_of_order_max_sec")
    @classmethod
    def _ooo_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("out_of_order_max_sec must be >= 0")
        return value


class RotationConfig(BaseModel):
    max_bytes: int = 5_000_000
    interval_sec: int = 60

    @field_validator("max_bytes", "interval_sec")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("rotation values must be > 0")
        return value


class SpikeConfig(BaseModel):
    probability_per_minute: float = 0.12
    min_duration_sec: int = 8
    max_duration_sec: int = 25
    min_multiplier: float = 2.0
    max_multiplier: float = 5.0

    @field_validator("probability_per_minute")
    @classmethod
    def _prob_range(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("probability_per_minute must be in [0, 1]")
        return value

    @field_validator("min_duration_sec", "max_duration_sec")
    @classmethod
    def _dur_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("duration must be > 0")
        return value

    @model_validator(mode="after")
    def _dur_order(self) -> "SpikeConfig":
        if self.max_duration_sec < self.min_duration_sec:
            raise ValueError("max_duration_sec must be >= min_duration_sec")
        if self.max_multiplier < self.min_multiplier:
            raise ValueError("max_multiplier must be >= min_multiplier")
        return self


class SimulatorConfig(BaseModel):
    start_time: datetime | None = None
    services: list[ServiceConfig]
    envs: dict[str, float] = Field(default_factory=lambda: {"prod": 0.85, "stage": 0.1, "dev": 0.05})
    regions: dict[str, float] = Field(default_factory=lambda: {"us-east-1": 0.55, "eu-west-1": 0.3, "ap-south-1": 0.15})
    level_distribution: dict[str, float] = Field(
        default_factory=lambda: {"DEBUG": 0.08, "INFO": 0.7, "WARN": 0.14, "ERROR": 0.07, "FATAL": 0.01}
    )
    format_distribution: dict[str, float] = Field(
        default_factory=lambda: {
            "jsonl": 0.16,
            "csv": 0.12,
            "plain": 0.18,
            "logfmt": 0.12,
            "syslog": 0.12,
            "access": 0.12,
            "multiline": 0.1,
            "mixed": 0.08,
        }
    )
    http_methods: dict[str, float] = Field(default_factory=lambda: {"GET": 0.55, "POST": 0.25, "PUT": 0.1, "DELETE": 0.1})
    paths: list[str] = Field(
        default_factory=lambda: ["/auth/login", "/auth/refresh", "/billing/payments", "/api/v1/orders", "/api/v1/profile"]
    )
    tags_pool: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "team": ["platform", "payments", "identity", "frontend"],
            "tier": ["edge", "backend", "worker"],
            "source": ["api", "cron", "queue"],
        }
    )
    intensity_profile: list[IntensityWindow] = Field(default_factory=lambda: [IntensityWindow(end_sec=86_400, multiplier=1.0)])
    spikes: SpikeConfig = Field(default_factory=SpikeConfig)
    incidents: list[IncidentConfig] = Field(default_factory=list)
    noise: NoiseConfig = Field(default_factory=NoiseConfig)
    rotation: RotationConfig = Field(default_factory=RotationConfig)
    include_loki_labels: bool = True

    @field_validator("start_time")
    @classmethod
    def _start_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @field_validator("services")
    @classmethod
    def _services_non_empty(cls, value: list[ServiceConfig]) -> list[ServiceConfig]:
        if not value:
            raise ValueError("at least one service required")
        return value

    @field_validator("paths")
    @classmethod
    def _paths_non_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("at least one path required")
        return value

    @field_validator("envs", "regions", "level_distribution", "http_methods", mode="after")
    @classmethod
    def _validate_distribution(cls, value: dict[str, float]) -> dict[str, float]:
        _assert_distribution(value)
        return value

    @field_validator("format_distribution", mode="after")
    @classmethod
    def _validate_formats(cls, value: dict[str, float]) -> dict[str, float]:
        _assert_distribution(value)
        unknown = set(value.keys()) - set(SUPPORTED_FORMATS)
        if unknown:
            raise ValueError(f"unsupported format(s): {', '.join(sorted(unknown))}")
        return value

    @model_validator(mode="after")
    def _validate_incident_services(self) -> "SimulatorConfig":
        service_names = {service.name for service in self.services}
        for incident in self.incidents:
            unknown = set(incident.affected_services) - service_names
            if unknown:
                names = ", ".join(sorted(unknown))
                raise ValueError(f"incident references unknown services: {names}")
        return self

    def normalized_distribution(self, source: Mapping[str, float]) -> dict[str, float]:
        total = sum(source.values())
        return {key: value / total for key, value in source.items()}

    def effective_noise(self, challenge_mode: bool) -> NoiseConfig:
        if not challenge_mode:
            return self.noise
        return NoiseConfig(
            duplicate_rate=min(1.0, self.noise.duplicate_rate * 2.5),
            out_of_order_rate=min(1.0, self.noise.out_of_order_rate * 2.0),
            out_of_order_max_sec=max(5, int(self.noise.out_of_order_max_sec * 1.8)),
            missing_field_rate=min(1.0, self.noise.missing_field_rate * 1.8),
            malformed_rate=min(1.0, self.noise.malformed_rate * 4.0),
            timezone_variation_rate=min(1.0, self.noise.timezone_variation_rate * 2.0),
            truncated_multiline_rate=min(1.0, self.noise.truncated_multiline_rate * 2.0),
            mixed_json_rate=min(1.0, self.noise.mixed_json_rate),
        )


def _assert_distribution(values: Mapping[str, float]) -> None:
    if not values:
        raise ValueError("distribution map cannot be empty")
    total = 0.0
    for key, value in values.items():
        if value < 0:
            raise ValueError(f"negative weight for '{key}'")
        total += value
    if total <= 0:
        raise ValueError("distribution total must be > 0")


def load_config(path: str | Path) -> SimulatorConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        content: Any = yaml.safe_load(handle) or {}
    if not isinstance(content, dict):
        raise ValueError("config root must be a YAML object")
    try:
        return SimulatorConfig.model_validate(content)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
