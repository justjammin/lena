from __future__ import annotations

import logging
import sys

import click

from .config import load_config
from .runtime.session import run_session

_log = logging.getLogger(__name__)


@click.group()
def cli() -> None:
    """LENA — LangGraph-powered agent CLI."""


@cli.command()
@click.option("--task", "-t", default=None, help="Task to run (use '-' to read from stdin)")
@click.option("--config", "-c", type=click.Path(), default=None, help="Path to lena.config.yaml")
@click.option("--model", "-m", default=None, help="Override model from config")
def run(task: str | None, config: str | None, model: str | None) -> None:
    """Run a LENA session for the given task."""
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    # Resolve task: flag, stdin marker, or stdin default
    if task is None or task == "-":
        if sys.stdin.isatty() and task is None:
            raise click.UsageError("Provide --task or pipe via stdin")
        task_text = sys.stdin.read().strip()
    else:
        task_text = task.strip()

    if not task_text:
        raise click.UsageError("Task is empty")

    # Model override: patch config in-memory by side-stepping lru_cache
    if model or config:
        from .config import load_config as _lc
        # Clear cache so new config_path / model override takes effect
        _lc.cache_clear()

    from pathlib import Path
    config_path = Path(config) if config else None

    result = run_session(task_text, config_path=config_path, model_override=model)

    output = result.get("upstream_context") or ""
    click.echo(output)


@cli.command()
@click.option("--config", "-c", type=click.Path(), default=None, help="Path to lena.config.yaml")
def tui(config: str | None) -> None:
    """Launch the Mega Man TUI."""
    from .ui.tui import LenaTUI
    app = LenaTUI(config_path=config)
    app.run()


@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind host")
@click.option("--port", default=8080, help="Bind port")
@click.option("--config", "-c", type=click.Path(), default=None, help="Path to lena.config.yaml")
def serve(host: str, port: int, config: str | None) -> None:
    """Launch the Mega Man web UI."""
    import uvicorn
    from .ui.web import create_app
    app = create_app(config_path=config)
    uvicorn.run(app, host=host, port=port)
