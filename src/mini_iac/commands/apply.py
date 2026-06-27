# src/mini_iac/commands/apply.py
from pathlib import Path

import typer
from rich.console import Console

from mini_iac.commands.plan import render_plan
from mini_iac.docker_engine.client import get_docker_client
from mini_iac.exceptions import MiniIacError
from mini_iac.executor.runner import execute_plan
from mini_iac.parser.loader import load_spec
from mini_iac.planner.diff import ActionType, Plan, compute_diff
from mini_iac.planner.refresh import refresh_state
from mini_iac.state.history import save_snapshot
from mini_iac.state.store import StateStore
from mini_iac.planner.graph import build_batches, resolve_dependencies

console = Console()


def run_apply(
    spec_file: Path,
    state_file: Path,
    auto_approve: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    spec = load_spec(spec_file)
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
            console.print("[green]Nothing to apply — infrastructure is up to date.[/green]")
            return

        console.print(f"\n[bold]Plan for [cyan]{spec.project}[/cyan]:[/bold]\n")
        render_plan(actions, console)
        console.print(f"\n[bold]{len(non_noop)} change(s) to apply.[/bold]")

        if dry_run:
            console.print("[dim]\nDry run — no changes made.[/dim]")
            return

        if not auto_approve:
            confirmed = typer.confirm("\nApply these changes?")
            if not confirmed:
                console.print("Aborted.")
                raise typer.Exit(0)

        save_snapshot(state_file)

        network_name = spec.network.name if spec.network else None
        result = execute_plan(plan, store, spec.project, network_name, client, depends_on=depends_on)

        console.print("\n[bold]Apply results:[/bold]")
        for name in result.succeeded:
            console.print(f"  [green]✓[/green] {name}")
        for name in result.failed:
            console.print(f"  [red]✗[/red] {name}: {result.errors[name]}")
        for name in result.skipped:
            console.print(f"  [dim]○[/dim] {name} (skipped)")

        if result.failed:
            raise typer.Exit(1)
