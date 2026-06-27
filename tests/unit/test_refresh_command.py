"""Unit tests for the refresh command."""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mini_iac.state.models import ResourceRecord, State
from mini_iac.state.store import StateStore


def _make_record(name: str, rtype: str = "container") -> ResourceRecord:
    return ResourceRecord(
        id="abc123",
        name=name,
        resource_type=rtype,
        spec_hash="deadbeef",
        spec_dict={"name": name},
        depends_on=[],
        created_at=datetime.now(timezone.utc),
    )


def _make_state(project: str = "myapp", resources: dict | None = None) -> State:
    return State(
        version=1,
        project=project,
        resources=resources or {},
    )


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / ".iac-state.json"


def test_no_drift_prints_green_message(state_file, capsys):
    """When refreshed state matches current state, no drift is reported."""
    resources = {"container/web": _make_record("web")}
    current = _make_state(resources=resources)

    store = StateStore(state_file)
    store.save(current)

    # refreshed == current (no drift)
    with (
        patch("mini_iac.commands.refresh.get_docker_client") as mock_client,
        patch("mini_iac.commands.refresh.refresh_state", return_value=current) as mock_refresh,
        patch("mini_iac.commands.refresh.console") as mock_console,
    ):
        from mini_iac.commands.refresh import run_refresh
        run_refresh(state_file)

    mock_refresh.assert_called_once()
    # Should print no-drift message (green)
    printed_calls = [str(c) for c in mock_console.print.call_args_list]
    assert any("No drift detected" in c for c in printed_calls)


def test_drift_detected_shows_missing_resources(state_file):
    """When a resource is missing from Docker, it appears in the drift table."""
    resources = {
        "container/web": _make_record("web"),
        "container/db": _make_record("db"),
    }
    current = _make_state(resources=resources)

    store = StateStore(state_file)
    store.save(current)

    # refreshed only has "web" — "db" was removed externally
    refreshed = _make_state(resources={"container/web": _make_record("web")})

    with (
        patch("mini_iac.commands.refresh.get_docker_client"),
        patch("mini_iac.commands.refresh.refresh_state", return_value=refreshed),
        patch("mini_iac.commands.refresh.console") as mock_console,
    ):
        from mini_iac.commands.refresh import run_refresh
        run_refresh(state_file)

    # Should have printed a table (not a "no drift" message)
    printed_calls = [str(c) for c in mock_console.print.call_args_list]
    assert not any("No drift detected" in c for c in printed_calls)
    # Table should have been printed (the Table object is passed to console.print)
    assert mock_console.print.call_count >= 1  # table only (no state update)


def test_refresh_does_not_mutate_state_file(state_file):
    """refresh is read-only — it must never write to the state file."""
    from mini_iac.state.store import StateStore
    from mini_iac.state.models import State, ResourceRecord
    from datetime import datetime, timezone

    initial_state = State(version=1, project="test", resources={
        "container/db": ResourceRecord(
            id="abc", name="db", resource_type="container",
            spec_hash="xyz", created_at=datetime.now(timezone.utc),
        )
    })
    store = StateStore(state_file)
    store.save(initial_state)

    import os
    mtime_before = os.path.getmtime(state_file)

    with patch("mini_iac.commands.refresh.get_docker_client"), \
         patch("mini_iac.commands.refresh.refresh_state") as mock_refresh:
        # refresh_state returns a state with the resource removed (drift detected)
        mock_refresh.return_value = State(version=1, project="test", resources={})
        from mini_iac.commands.refresh import run_refresh
        run_refresh(state_file=state_file)

    mtime_after = os.path.getmtime(state_file)
    assert mtime_before == mtime_after, "refresh must not write to the state file"


def test_no_project_name_prints_warning(state_file):
    """When no project in state and no --project arg, a warning is printed."""
    empty_state = State(version=0, project="", resources={})
    store = StateStore(state_file)
    store.save(empty_state)

    with (
        patch("mini_iac.commands.refresh.get_docker_client"),
        patch("mini_iac.commands.refresh.console") as mock_console,
    ):
        from mini_iac.commands.refresh import run_refresh
        run_refresh(state_file, project=None)

    printed_calls = [str(c) for c in mock_console.print.call_args_list]
    assert any("No project name" in c for c in printed_calls)


def test_project_arg_overrides_state_project(state_file):
    """Explicit --project argument takes precedence over project in state."""
    current = _make_state(project="old-project", resources={})
    store = StateStore(state_file)
    store.save(current)

    refreshed = _make_state(project="old-project", resources={})

    with (
        patch("mini_iac.commands.refresh.get_docker_client") as mock_client,
        patch("mini_iac.commands.refresh.refresh_state", return_value=refreshed) as mock_refresh,
        patch("mini_iac.commands.refresh.console"),
    ):
        from mini_iac.commands.refresh import run_refresh
        run_refresh(state_file, project="new-project")

    # refresh_state should be called with the override project name
    call_args = mock_refresh.call_args
    assert call_args[0][1] == "new-project"  # second positional arg is project
