import json
import os
import pytest
from datetime import datetime, timezone
from pathlib import Path

from mini_iac.state.models import ResourceRecord, State
from mini_iac.state.store import StateStore
from mini_iac.exceptions import StateError


@pytest.fixture
def store(tmp_path):
    return StateStore(tmp_path / ".iac-state.json")


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


def test_load_returns_empty_state_when_file_absent(store):
    state = store.load()
    assert state.resources == {}
    assert state.version == 0


def test_save_and_load_roundtrip(store):
    state = State(version=1, project="myapp", resources={"container/web": _make_record("web")})
    store.save(state)
    loaded = store.load()
    assert loaded.version == 1
    assert loaded.project == "myapp"
    assert "container/web" in loaded.resources


def test_save_is_atomic(store, tmp_path):
    state = State(version=1, project="test", resources={})
    store.save(state)
    assert store.state_file.exists()
    assert not (tmp_path / ".iac-state.tmp").exists()


def test_lock_creates_lock_file(store):
    store.lock()
    assert store._lock_file.exists()
    data = json.loads(store._lock_file.read_text())
    assert data["pid"] == os.getpid()
    assert "timestamp" in data
    store.unlock()


def test_unlock_removes_lock_file(store):
    store.lock()
    store.unlock()
    assert not store._lock_file.exists()


def test_lock_raises_if_already_locked_by_live_process(store):
    store.lock()
    try:
        with pytest.raises(StateError, match="locked by PID"):
            store.lock()
    finally:
        store.unlock()


def test_lock_clears_stale_lock(store):
    # Write a lock with a PID that definitely doesn't exist
    store._lock_file.write_text(
        json.dumps({"pid": 99999999, "timestamp": "2020-01-01T00:00:00"})
    )
    store.lock()  # should clear stale lock and acquire
    assert store._lock_file.exists()
    store.unlock()


def test_locked_context_manager(store):
    with store.locked():
        assert store._lock_file.exists()
    assert not store._lock_file.exists()
