from __future__ import annotations

import re
from pathlib import Path

from logs_simulator.config import load_config
from logs_simulator.generator import SimulationEngine

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def test_event_id_present_in_raw_logs(tmp_path: Path, write_config) -> None:
    config_path = write_config(
        overrides={
            "format_distribution": {
                "jsonl": 0.2,
                "csv": 0.15,
                "plain": 0.2,
                "logfmt": 0.15,
                "syslog": 0.15,
                "access": 0.15,
                "multiline": 0.0,
                "mixed": 0.0,
            },
            "noise": {"malformed_rate": 0.0},
        }
    )
    config = load_config(config_path)

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    engine = SimulationEngine(
        config=config,
        out_dir=out_dir,
        duration_sec=20,
        events_per_sec=30,
        seed=101,
        challenge_mode=False,
        use_gzip=False,
    )
    engine.generate()

    raw_files = [path for path in out_dir.rglob("*") if path.is_file() and "ground_truth" not in path.parts]
    assert raw_files

    for file_path in raw_files:
        for idx, line in enumerate(file_path.read_text(encoding="utf-8").splitlines()):
            if idx == 0 and file_path.suffix == ".csv" and line.startswith("event_id,"):
                continue
            if not line.strip():
                continue
            assert UUID_RE.search(line), f"missing event_id UUID in {file_path}: {line}"


def test_ground_truth_count_is_consistent_with_raw_logs(tmp_path: Path, write_config) -> None:
    config_path = write_config(
        overrides={
            "noise": {
                "malformed_rate": 0.08,
                "duplicate_rate": 0.04,
            }
        }
    )
    config = load_config(config_path)

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    engine = SimulationEngine(
        config=config,
        out_dir=out_dir,
        duration_sec=35,
        events_per_sec=40,
        seed=777,
        challenge_mode=True,
        use_gzip=False,
    )
    engine.generate()

    gt_files = [path for path in out_dir.rglob("ground_truth.jsonl")]
    assert gt_files, "ground_truth.jsonl not found"

    gt_count = sum(len(path.read_text(encoding="utf-8").splitlines()) for path in gt_files)
    assert gt_count > 0

    raw_files = [path for path in out_dir.rglob("*") if path.is_file() and "ground_truth" not in path.parts]
    raw_mentions = 0
    for file_path in raw_files:
        raw_mentions += len(UUID_RE.findall(file_path.read_text(encoding="utf-8")))

    tolerance = int(gt_count * 0.3) + 40
    assert raw_mentions >= gt_count
    assert raw_mentions <= gt_count + tolerance
