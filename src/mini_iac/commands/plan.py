from pathlib import Path

from rich.console import Console

from mini_iac.docker_engine.client import get_docker_client
from mini_iac.exceptions import MiniIacError
from mini_iac.parser.loader import load_spec
from mini_iac.planner.diff import ActionType, Plan, compute_diff
from mini_iac.planner.graph import build_batches
from mini_iac.planner.refresh import refresh_state
from mini_iac.state.store import StateStore

console = Console()

_SYMBOLS = {
    ActionType.CREATE:  ("[green]+[/green]", "create"),
    ActionType.UPDATE:  ("[yellow]~[/yellow]", "update"),
    ActionType.DESTROY: ("[red]-[/red]", "destroy"),
    ActionType.NOOP:    ("[dim]0[/dim]", "no change"),
}


def render_plan(actions, out: Console) -> None:
    for action in actions:
        symbol, label = _SYMBOLS[action.action_type]
        resource = f"{action.resource_type}/{action.resource_name}"
        out.print(f"  {symbol} {resource}  [dim]({label}: {action.reason})[/dim]")


def run_plan(spec_file: Path, state_file: Path, verbose: bool = False) -> Plan:
    spec = load_spec(spec_file)
    client = get_docker_client()
    store = StateStore(state_file)
    current = store.load()
    refreshed = refresh_state(current, spec.project, client)

    actions = compute_diff(spec, refreshed)
    active_action_names = {a.resource_name for a in actions if a.action_type != ActionType.NOOP}
    network_name = spec.network.name if spec.network else None

    depends_on: dict[str, list[str]] = {}
    for c in spec.containers:
        deps = list(c.depends_on)
        if network_name and network_name in active_action_names:
            deps.append(network_name)
        for vol_str in c.volumes:
            vol_name = vol_str.split(":")[0]
            if vol_name in active_action_names:
                deps.append(vol_name)
        depends_on[c.name] = deps

    batches = build_batches(actions, depends_on)
    plan = Plan(actions=actions, batches=batches)

    console.print(f"\n[bold]Plan for [cyan]{spec.project}[/cyan]:[/bold]\n")
    render_plan(actions, console)

    non_noop = [a for a in actions if a.action_type != ActionType.NOOP]
    summary = f"\n[bold]{len(non_noop)} change(s) to apply.[/bold]"
    if not non_noop:
        summary = "\n[green]No changes — infrastructure is up to date.[/green]"
    console.print(summary)

    return plan
