from __future__ import annotations

from pathlib import Path

from logs_simulator.config import load_config
from logs_simulator.generator import SimulationEngine


EXPECTED_FORMATS = {"jsonl", "csv", "plain", "logfmt", "syslog", "access", "multiline", "mixed"}


def test_generates_all_required_formats(tmp_path: Path, write_config) -> None:
    config_path = write_config(overrides={"noise": {"malformed_rate": 0.0}})
    config = load_config(config_path)

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    engine = SimulationEngine(
        config=config,
        out_dir=out_dir,
        duration_sec=50,
        events_per_sec=55,
        seed=17,
        challenge_mode=False,
        use_gzip=False,
    )
    stats = engine.generate()

    observed = {part for path in stats.output_files for part in Path(path).parts if part in EXPECTED_FORMATS}
    assert EXPECTED_FORMATS.issubset(observed)
