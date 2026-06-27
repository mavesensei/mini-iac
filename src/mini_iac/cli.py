from pathlib import Path

import typer
from rich.console import Console

from mini_iac.exceptions import MiniIacError

app = typer.Typer(name="iac", help="Infrastructure-as-Code engine for Docker", add_completion=False)
console = Console()


@app.callback(invoke_without_command=True)
def _callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@app.command()
def plan(
    file: Path = typer.Argument(..., help="Path to the spec YAML file", exists=True),
    state_file: Path = typer.Option(Path(".iac-state.json"), "--state-file", help="State file path"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Verbose output"),
) -> None:
    """Show what changes would be applied without making any."""
    from mini_iac.commands.plan import run_plan
    try:
        run_plan(file, state_file, verbose)
    except MiniIacError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def apply(
    file: Path = typer.Argument(..., help="Path to the spec YAML file", exists=True),
    state_file: Path = typer.Option(Path(".iac-state.json"), "--state-file"),
    auto_approve: bool = typer.Option(False, "--auto-approve", "-y"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
) -> None:
    """Apply the spec — create, update, or destroy resources to match desired state."""
    from mini_iac.commands.apply import run_apply
    try:
        run_apply(file, state_file, auto_approve, dry_run, verbose)
    except MiniIacError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def destroy(
    state_file: Path = typer.Option(Path(".iac-state.json"), "--state-file"),
    auto_approve: bool = typer.Option(False, "--auto-approve", "-y"),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
) -> None:
    """Destroy all resources tracked in state."""
    from mini_iac.commands.destroy import run_destroy
    try:
        run_destroy(state_file, auto_approve, verbose)
    except MiniIacError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def refresh(
    state_file: Path = typer.Option(Path(".iac-state.json"), "--state-file"),
    project: str | None = typer.Option(None, "--project"),
) -> None:
    """Detect drift between state file and live Docker resources."""
    from mini_iac.commands.refresh import run_refresh
    try:
        run_refresh(state_file, project)
    except MiniIacError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def rollback(
    state_file: Path = typer.Option(Path(".iac-state.json"), "--state-file", help="State file path"),
    to_version: int | None = typer.Option(None, "--to-version", "-n", help="Snapshot version to restore"),
    auto_approve: bool = typer.Option(False, "--auto-approve", "-y"),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
) -> None:
    """Rollback to a previous state snapshot."""
    from mini_iac.commands.rollback import run_rollback
    try:
        run_rollback(state_file, to_version, auto_approve, verbose)
    except MiniIacError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def main() -> None:
    app()
