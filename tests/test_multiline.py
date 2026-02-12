from __future__ import annotations

from pathlib import Path

from logs_simulator.config import load_config
from logs_simulator.generator import SimulationEngine


def test_multiline_entries_are_long_and_stacktrace_like(tmp_path: Path, write_config) -> None:
    config_path = write_config(
        overrides={
            "format_distribution": {
                "jsonl": 0.0,
                "csv": 0.0,
                "plain": 0.0,
                "logfmt": 0.0,
                "syslog": 0.0,
                "access": 0.0,
                "multiline": 1.0,
                "mixed": 0.0,
            },
            "noise": {"malformed_rate": 0.0, "timezone_variation_rate": 0.0},
        }
    )
    config = load_config(config_path)

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    engine = SimulationEngine(
        config=config,
        out_dir=out_dir,
        duration_sec=8,
        events_per_sec=18,
        seed=99,
        challenge_mode=True,
        use_gzip=False,
    )
    engine.generate()

    multiline_files = [path for path in out_dir.rglob("*.log") if "multiline" in path.parts]
    assert multiline_files, "no multiline files generated"

    content = "\n".join(path.read_text(encoding="utf-8") for path in multiline_files)
    lines = content.splitlines()

    event_starts = [idx for idx, line in enumerate(lines) if "event_id=" in line]
    assert event_starts, "no event starts with event_id in multiline output"

    max_gap = 0
    for left, right in zip(event_starts, event_starts[1:]):
        max_gap = max(max_gap, right - left)
    if len(event_starts) == 1:
        max_gap = len(lines)

    assert max_gap >= 10
    assert any(token in content for token in ("Traceback", "Caused by", "UnhandledPromiseRejection", "Suppressed"))
