# src/mini_iac/commands/destroy.py
from pathlib import Path

import typer
from rich.console import Console

from mini_iac.docker_engine.client import get_docker_client
from mini_iac.exceptions import MiniIacError
from mini_iac.executor.runner import execute_plan
from mini_iac.planner.diff import Action, ActionType, Plan, ResourceType
from mini_iac.state.store import StateStore
from mini_iac.planner.graph import build_batches, resolve_dependencies
from mini_iac.planner.refresh import refresh_state

console = Console()


def _build_destroy_plan(state, depends_on: dict[str, list[str]] | None = None) -> Plan:
    actions = [
        Action(
            resource_type=ResourceType(rtype),
            resource_name=rname,
            action_type=ActionType.DESTROY,
            reason="destroy all",
            current=record.spec_dict,
        )
        for key, record in state.resources.items()
        for rtype, rname in [key.split("/", 1)]
    ]
    batches = build_batches(actions, depends_on or {}, is_destroy=True)
    return Plan(actions=actions, batches=batches)


def run_destroy(
    state_file: Path,
    auto_approve: bool = False,
    verbose: bool = False,
) -> None:
    store = StateStore(state_file)

    with store.locked():
        state = store.load()
        client = get_docker_client()
        state = refresh_state(state, state.project, client)
        if not state.resources:
            console.print("[green]Nothing to destroy — state is empty.[/green]")
            return

        # Reconstruct dependency info from stored records
        network_name = next(
            (rname for key, record in state.resources.items()
            for rtype, rname in [key.split("/", 1)]
            if rtype == "network"),
            None,
        )

        containers_info = [
            (rname, record.depends_on, [v.split(":")[0] for v in (record.spec_dict or {}).get("volumes", [])])
            for key, record in state.resources.items()
            for rtype, rname in [key.split("/", 1)]
            if rtype == "container"
        ]

        depends_on = resolve_dependencies(containers_info, network_name)

        plan = _build_destroy_plan(state, depends_on)

        console.print(f"\n[bold]Destroy plan for [cyan]{state.project}[/cyan]:[/bold]\n")
        for action in plan.actions:
            console.print(f"  [red]-[/red] {action.resource_type}/{action.resource_name}  [dim](destroy)[/dim]")
        console.print(f"\n[bold]{len(plan.actions)} resource(s) will be destroyed.[/bold]")

        if not auto_approve:
            typer.confirm("Destroy all resources?", abort=True)

        client = get_docker_client()
        result = execute_plan(plan, store, state.project, None, client, depends_on=depends_on)

        for name in result.succeeded:
            console.print(f"  [green]✓[/green] {name} destroyed")
        for name in result.failed:
            console.print(f"  [red]✗[/red] {name}: {result.errors[name]}")
        for name in result.skipped:
            console.print(f"  [dim]○[/dim] {name}  [dim](skipped)[/dim]")

        if result.failed:
            raise typer.Exit(1)
