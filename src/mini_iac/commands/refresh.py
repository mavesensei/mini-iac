# src/mini_iac/commands/refresh.py
from pathlib import Path

from rich.console import Console
from rich.table import Table

from mini_iac.docker_engine.client import get_docker_client
from mini_iac.state.models import State
from mini_iac.state.store import StateStore
from mini_iac.planner.refresh import refresh_state

console = Console()


def run_refresh(state_file: Path, project: str | None = None) -> None:
    store = StateStore(state_file)
    current = store.load()
    proj = project or current.project
    if not proj:
        console.print("[yellow]No project name — run apply first or pass --project.[/yellow]")
        return

    client = get_docker_client()
    refreshed = refresh_state(current, proj, client)

    drifted = {k for k in current.resources if k not in refreshed.resources}

    if not drifted:
        console.print("[green]No drift detected — state matches live Docker resources.[/green]")
    else:
        table = Table(title="Drift Detected")
        table.add_column("Resource", style="red")
        table.add_column("Status")
        for key in drifted:
            table.add_row(key, "missing from Docker (removed externally)")
        console.print(table)
