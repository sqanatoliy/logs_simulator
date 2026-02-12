from __future__ import annotations

import hashlib
from pathlib import Path

from logs_simulator.config import load_config
from logs_simulator.generator import SimulationEngine


def _run_generation(config_path: Path, out_dir: Path, seed: int) -> None:
    config = load_config(config_path)
    engine = SimulationEngine(
        config=config,
        out_dir=out_dir,
        duration_sec=30,
        events_per_sec=35,
        seed=seed,
        challenge_mode=False,
        use_gzip=False,
    )
    engine.generate()


def _manifest(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
        relative = str(file_path.relative_to(root))
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        result[relative] = digest
    return result


def test_seed_produces_deterministic_output(tmp_path: Path, write_config) -> None:
    config_path = write_config()

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    out_a.mkdir()
    out_b.mkdir()

    _run_generation(config_path, out_a, seed=123)
    _run_generation(config_path, out_b, seed=123)

    assert _manifest(out_a) == _manifest(out_b)
