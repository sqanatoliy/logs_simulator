from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml


def build_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    config: dict[str, Any] = {
        "start_time": "2026-02-12T10:00:00Z",
        "services": [
            {"name": "auth", "weight": 1.2},
            {"name": "billing", "weight": 1.0},
            {"name": "api-gateway", "weight": 1.4},
            {"name": "worker", "weight": 0.8},
        ],
        "envs": {"prod": 0.85, "stage": 0.1, "dev": 0.05},
        "regions": {"us-east-1": 0.6, "eu-west-1": 0.3, "ap-south-1": 0.1},
        "level_distribution": {"DEBUG": 0.08, "INFO": 0.7, "WARN": 0.14, "ERROR": 0.07, "FATAL": 0.01},
        "format_distribution": {
            "jsonl": 0.16,
            "csv": 0.12,
            "plain": 0.18,
            "logfmt": 0.12,
            "syslog": 0.12,
            "access": 0.12,
            "multiline": 0.1,
            "mixed": 0.08,
        },
        "http_methods": {"GET": 0.55, "POST": 0.25, "PUT": 0.1, "DELETE": 0.1},
        "paths": ["/auth/login", "/auth/refresh", "/billing/payments", "/api/v1/orders", "/api/v1/profile"],
        "tags_pool": {
            "team": ["platform", "payments", "identity"],
            "tier": ["edge", "backend", "worker"],
            "source": ["api", "cron", "queue"],
        },
        "intensity_profile": [
            {"start_sec": 0, "end_sec": 3600, "multiplier": 1.0},
        ],
        "spikes": {
            "probability_per_minute": 0.0,
            "min_duration_sec": 5,
            "max_duration_sec": 15,
            "min_multiplier": 2.0,
            "max_multiplier": 4.0,
        },
        "incidents": [
            {
                "start_sec": 15,
                "duration_sec": 120,
                "affected_services": ["api-gateway", "auth"],
                "error_rate_multiplier": 3.0,
                "latency_multiplier": 2.0,
                "five_xx_boost": 0.2,
            }
        ],
        "noise": {
            "duplicate_rate": 0.02,
            "out_of_order_rate": 0.03,
            "out_of_order_max_sec": 8,
            "missing_field_rate": 0.06,
            "malformed_rate": 0.01,
            "timezone_variation_rate": 0.05,
            "truncated_multiline_rate": 0.12,
            "mixed_json_rate": 0.45,
        },
        "rotation": {"max_bytes": 4_000_000, "interval_sec": 60},
        "include_loki_labels": True,
    }

    if overrides:
        _deep_update(config, overrides)
    return config


def _deep_update(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


@pytest.fixture
def write_config(tmp_path: Path):
    def _writer(name: str = "config.yaml", overrides: dict[str, Any] | None = None) -> Path:
        path = tmp_path / name
        payload = build_config(overrides)
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        return path

    return _writer
