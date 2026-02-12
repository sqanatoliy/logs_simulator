from __future__ import annotations

from pathlib import Path

import typer

from .config import load_config
from .generator import SimulationEngine

app = typer.Typer(help="Production-like logs simulator for parser/normalizer testing")


@app.command("validate-config")
def validate_config(
    config: Path = typer.Option(..., "--config", exists=True, dir_okay=False, readable=True, help="Path to YAML config"),
) -> None:
    """Validate YAML config."""
    loaded = load_config(config)
    typer.echo("Config is valid")
    typer.echo(f"services={len(loaded.services)} formats={','.join(loaded.format_distribution.keys())}")


@app.command("generate")
def generate(
    config: Path = typer.Option(..., "--config", exists=True, dir_okay=False, readable=True, help="Path to YAML config"),
    out_dir: Path = typer.Option(Path("./logs_out"), "--out-dir", help="Output directory"),
    duration_sec: int = typer.Option(600, "--duration-sec", min=1, help="Simulation duration in seconds"),
    events_per_sec: int = typer.Option(200, "--events-per-sec", min=1, help="Base events per second"),
    seed: int = typer.Option(42, "--seed", help="RNG seed for deterministic output"),
    gzip: bool = typer.Option(False, "--gzip", help="Write gzip-compressed files"),
    challenge_mode: bool = typer.Option(False, "--challenge-mode", help="Increase noise and malformed cases"),
) -> None:
    """Generate logs for fixed duration."""
    loaded = load_config(config)
    out_dir.mkdir(parents=True, exist_ok=True)

    engine = SimulationEngine(
        config=loaded,
        out_dir=out_dir,
        duration_sec=duration_sec,
        events_per_sec=events_per_sec,
        seed=seed,
        challenge_mode=challenge_mode,
        use_gzip=gzip,
    )
    stats = engine.generate()

    typer.echo(
        "generated "
        f"events={stats.total_events} duplicates={stats.duplicates} malformed={stats.malformed_lines} files={len(stats.output_files)}"
    )


@app.command("stream")
def stream(
    config: Path = typer.Option(..., "--config", exists=True, dir_okay=False, readable=True, help="Path to YAML config"),
    out_dir: Path = typer.Option(Path("./logs_out"), "--out-dir", help="Output directory"),
    duration_sec: int | None = typer.Option(
        None, "--duration-sec", min=1, help="Optional duration for stream mode; default is infinite"
    ),
    events_per_sec: int = typer.Option(200, "--events-per-sec", min=1, help="Base events per second"),
    seed: int = typer.Option(42, "--seed", help="RNG seed"),
    gzip: bool = typer.Option(False, "--gzip", help="Write gzip-compressed files"),
    challenge_mode: bool = typer.Option(False, "--challenge-mode", help="Increase noise and malformed cases"),
) -> None:
    """Continuously generate logs (Ctrl+C to stop)."""
    loaded = load_config(config)
    out_dir.mkdir(parents=True, exist_ok=True)

    engine = SimulationEngine(
        config=loaded,
        out_dir=out_dir,
        duration_sec=duration_sec or 1,
        events_per_sec=events_per_sec,
        seed=seed,
        challenge_mode=challenge_mode,
        use_gzip=gzip,
    )
    stats = engine.stream(duration_sec=duration_sec)

    typer.echo(
        "stream finished "
        f"events={stats.total_events} duplicates={stats.duplicates} malformed={stats.malformed_lines} files={len(stats.output_files)}"
    )


if __name__ == "__main__":
    app()
