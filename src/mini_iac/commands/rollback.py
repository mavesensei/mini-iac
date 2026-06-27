# src/mini_iac/commands/rollback.py
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from mini_iac.commands.plan import render_plan
from mini_iac.docker_engine.client import get_docker_client
from mini_iac.exceptions import MiniIacError
from mini_iac.executor.runner import execute_plan
from mini_iac.planner.diff import ActionType, Plan, compute_diff
from mini_iac.planner.graph import build_batches, resolve_dependencies
from mini_iac.planner.refresh import refresh_state
from mini_iac.state.history import list_snapshots, load_snapshot, save_snapshot, state_to_spec
from mini_iac.state.store import StateStore

console = Console()


def run_rollback(
    state_file: Path,
    to_version: int | None = None,
    auto_approve: bool = False,
    verbose: bool = False,
) -> None:
    """Restore infrastructure to match a previous state snapshot.

    This re-derives an AppSpec from the snapshot and runs it through the same
    plan/diff/execute pipeline as `apply` — rollback is apply with an old desired state.
    """
    versions = list_snapshots(state_file)
    if not versions:
        console.print("[yellow]No snapshots available.[/yellow]")
        return

    if to_version is None:
        table = Table(title="Available Snapshots")
        table.add_column("Version", style="cyan")
        table.add_column("File")
        for v in versions:
            table.add_row(str(v), f"{state_file.stem}.v{v}.json")
        console.print(table)
        to_version = typer.prompt("Rollback to version", type=int)

    if to_version not in versions:
        console.print(
            f"[red]Version {to_version} not found. Available: {versions}[/red]"
        )
        raise typer.Exit(1)

    target_state = load_snapshot(to_version, state_file)
    current_check = StateStore(state_file).load()
    if current_check.project and target_state.project != current_check.project:
        console.print(
            f"[red]Refusing to rollback: snapshot v{to_version} belongs to project "
            f"'{target_state.project}', but current state is for project "
            f"'{current_check.project}'.[/red]"
        )
        raise typer.Exit(1)
    
    spec = state_to_spec(target_state)

    client = get_docker_client()
    store = StateStore(state_file)

    with store.locked():
        current = store.load()
        refreshed = refresh_state(current, spec.project, client)

        containers_info = [
            (c.name, c.depends_on, [v.split(":")[0] for v in c.volumes])
            for c in spec.containers
        ]
        network_name_for_deps = spec.network.name if spec.network else None
        depends_on = resolve_dependencies(containers_info, network_name_for_deps)

        actions = compute_diff(spec, refreshed)
        batches = build_batches(actions, depends_on)
        plan = Plan(actions=actions, batches=batches)

        non_noop = [a for a in actions if a.action_type != ActionType.NOOP]
        if not non_noop:
            console.print(
                f"[green]Already matches snapshot v{to_version} — nothing to change.[/green]"
            )
            return

        console.print(f"\n[bold]Rollback plan to snapshot v{to_version} for [cyan]{spec.project}[/cyan]:[/bold]\n")
        render_plan(actions, console)
        console.print(f"\n[bold]{len(non_noop)} change(s) to apply.[/bold]")

        if not auto_approve:
            confirmed = typer.confirm("\nReconcile infrastructure to this snapshot?")
            if not confirmed:
                console.print("Aborted.")
                raise typer.Exit(0)

        save_snapshot(state_file)
        network_name = spec.network.name if spec.network else None
        result = execute_plan(plan, store, spec.project, network_name, client, depends_on=depends_on)

    console.print("\n[bold]Rollback results:[/bold]")
    for name in result.succeeded:
        console.print(f"  [green]✓[/green] {name}")
    for name in result.failed:
        console.print(f"  [red]✗[/red] {name}: {result.errors[name]}")
    for name in result.skipped:
        console.print(f"  [dim]○[/dim] {name} (skipped)")

    if result.failed:
        raise typer.Exit(1)