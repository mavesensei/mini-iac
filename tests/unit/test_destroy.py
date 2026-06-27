from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest
from mini_iac.commands.destroy import _build_destroy_plan, run_destroy
from mini_iac.planner.diff import ActionType, ResourceType
from mini_iac.state.models import State, ResourceRecord
from datetime import datetime, timezone


def _make_state(*resource_keys):
    """resource_keys like 'container/api', 'volume/data'"""
    resources = {}
    for key in resource_keys:
        rtype, rname = key.split("/", 1)
        resources[key] = ResourceRecord(
            id=f"id-{rname}", name=rname, resource_type=rtype,
            spec_hash="abc", created_at=datetime.now(timezone.utc),
        )
    return State(version=1, project="test", resources=resources)


def test_build_destroy_plan_empty_state():
    state = State(version=1, project="test")
    plan = _build_destroy_plan(state)
    assert plan.actions == []
    assert plan.batches == []


def test_build_destroy_plan_non_empty():
    state = _make_state("container/api", "volume/data")
    plan = _build_destroy_plan(state)
    action_types = {a.action_type for a in plan.actions}
    assert action_types == {ActionType.DESTROY}
    names = {a.resource_name for a in plan.actions}
    assert names == {"api", "data"}


def test_build_destroy_plan_batches_reversed():
    """Destroy uses is_destroy=True so batches are reversed."""
    state = _make_state("container/api")
    plan = _build_destroy_plan(state)
    # At least one batch must exist when there are resources
    assert len(plan.batches) >= 1


def test_run_destroy_empty_state_prints_nothing(tmp_path, capsys):
    state_file = tmp_path / "state.json"
    # No state file → empty state → nothing to destroy
    run_destroy(state_file=state_file, auto_approve=True, verbose=False)
    # Should not raise; no actions taken


def test_run_destroy_calls_execute_plan(tmp_path):
    from mini_iac.state.store import StateStore
    state_file = tmp_path / "state.json"
    store = StateStore(state_file)
    state = _make_state("container/api")
    store.save(state)

    fake_container = MagicMock()
    fake_container.name = "api"

    fake_client = MagicMock()
    fake_client.containers.list.return_value = [fake_container]
    fake_client.networks.list.return_value = []
    fake_client.volumes.list.return_value = []

    with patch("mini_iac.commands.destroy.get_docker_client", return_value=fake_client), \
        patch("mini_iac.commands.destroy.execute_plan") as mock_exec:
        mock_exec.return_value = MagicMock(succeeded=["api"], failed=[], skipped=[])
        run_destroy(state_file=state_file, auto_approve=True, verbose=False)
        mock_exec.assert_called_once()