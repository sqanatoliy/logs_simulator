#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from logs_simulator.config import load_config
from logs_simulator.generator import SimulationEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a quick sample logs dataset")
    parser.add_argument("--config", default="config.example.yaml", help="Path to config YAML")
    parser.add_argument("--out-dir", default="./sample_dataset", help="Output directory")
    parser.add_argument("--duration-sec", type=int, default=120, help="Duration in seconds")
    parser.add_argument("--events-per-sec", type=int, default=80, help="Base events per second")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--challenge-mode", action="store_true", help="Enable high-noise generation")
    args = parser.parse_args()

    config = load_config(args.config)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    engine = SimulationEngine(
        config=config,
        out_dir=out_dir,
        duration_sec=args.duration_sec,
        events_per_sec=args.events_per_sec,
        seed=args.seed,
        challenge_mode=args.challenge_mode,
        use_gzip=False,
    )
    stats = engine.generate()
    print(
        f"sample dataset created: events={stats.total_events}, duplicates={stats.duplicates}, "
        f"malformed={stats.malformed_lines}, files={len(stats.output_files)}"
    )


if __name__ == "__main__":
    main()
