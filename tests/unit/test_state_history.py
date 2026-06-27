# tests/unit/test_state_history.py
import pytest
from pathlib import Path

from mini_iac.state.history import list_snapshots, load_snapshot, save_snapshot
from mini_iac.state.models import State
from mini_iac.exceptions import StateError


def _state(version: int) -> State:
    return State(version=version, project="test", resources={})


def test_save_snapshot_creates_versioned_file(tmp_path):
    state_file = tmp_path / ".iac-state.json"
    state_file.write_text(State(version=1, project="test").model_dump_json())
    save_snapshot(state_file)
    assert (tmp_path / ".iac-state.v1.json").exists()


def test_save_snapshot_increments_version(tmp_path):
    state_file = tmp_path / ".iac-state.json"
    state_file.write_text(State(version=1, project="test").model_dump_json())
    save_snapshot(state_file)
    state_file.write_text(State(version=2, project="test").model_dump_json())
    save_snapshot(state_file)
    assert (tmp_path / ".iac-state.v1.json").exists()
    assert (tmp_path / ".iac-state.v2.json").exists()


def test_save_snapshot_noop_when_no_state_file(tmp_path):
    state_file = tmp_path / ".iac-state.json"
    # No state file — should not raise
    save_snapshot(state_file)
    assert list(tmp_path.glob("*.json")) == []


def test_list_snapshots_returns_versions(tmp_path):
    state_file = tmp_path / ".iac-state.json"
    (tmp_path / ".iac-state.v1.json").write_text("{}")
    (tmp_path / ".iac-state.v3.json").write_text("{}")
    versions = list_snapshots(state_file)
    assert sorted(versions) == [1, 3]


def test_list_snapshots_empty_when_none(tmp_path):
    state_file = tmp_path / ".iac-state.json"
    versions = list_snapshots(state_file)
    assert versions == []


def test_load_snapshot_returns_state(tmp_path):
    state_file = tmp_path / ".iac-state.json"
    s = State(version=5, project="snap")
    (tmp_path / ".iac-state.v5.json").write_text(s.model_dump_json())
    loaded = load_snapshot(5, state_file)
    assert loaded.version == 5
    assert loaded.project == "snap"


def test_load_snapshot_missing_raises_state_error(tmp_path):
    state_file = tmp_path / ".iac-state.json"
    with pytest.raises(StateError, match="Snapshot v99 not found"):
        load_snapshot(99, state_file)
