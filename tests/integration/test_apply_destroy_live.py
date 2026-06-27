"""
Integration tests for apply and destroy flows.

Requires a live Docker daemon.
Run with: pytest -m integration -v
"""
import pytest
import docker
from pathlib import Path

from mini_iac.docker_engine.client import get_docker_client
from mini_iac.executor.runner import execute_plan
from mini_iac.parser.loader import load_spec
from mini_iac.planner.diff import Plan, compute_diff
from mini_iac.planner.graph import build_batches
from mini_iac.planner.refresh import refresh_state
from mini_iac.state.store import StateStore

SINGLE_CONTAINER = Path(__file__).parent.parent.parent / "examples" / "single-container.yaml"


@pytest.mark.integration
def test_apply_creates_container(tmp_path):
    state_file = tmp_path / ".iac-state.json"
    spec = load_spec(SINGLE_CONTAINER)
    client = get_docker_client()
    store = StateStore(state_file)

    current = store.load()
    refreshed = refresh_state(current, spec.project, client)
    depends_on = {c.name: c.depends_on for c in spec.containers}
    actions = compute_diff(spec, refreshed)
    batches = build_batches(actions, depends_on)
    plan = Plan(actions=actions, batches=batches)
    network_name = spec.network.name if spec.network else None

    result = execute_plan(plan, store, spec.project, network_name, client)

    try:
        assert not result.failed, f"Failed: {result.errors}"
        container = client.containers.get("web")
        assert container.status == "running"
    finally:
        # Cleanup even if assertions fail
        try:
            c = client.containers.get("web")
            c.stop()
            c.remove()
        except docker.errors.NotFound:
            pass
        try:
            client.networks.get("single-net").remove()
        except docker.errors.NotFound:
            pass


@pytest.mark.integration
def test_apply_then_destroy(tmp_path):
    state_file = tmp_path / ".iac-state.json"
    spec = load_spec(SINGLE_CONTAINER)
    client = get_docker_client()
    store = StateStore(state_file)

    try:
        # Apply
        current = store.load()
        refreshed = refresh_state(current, spec.project, client)
        depends_on = {c.name: c.depends_on for c in spec.containers}
        actions = compute_diff(spec, refreshed)
        plan = Plan(actions=actions, batches=build_batches(actions, depends_on))
        network_name = spec.network.name if spec.network else None
        execute_plan(plan, store, spec.project, network_name, client)

        # Destroy
        from mini_iac.commands.destroy import _build_destroy_plan
        state = store.load()
        destroy_deps = {
            rname: record.depends_on
            for key, record in state.resources.items()
            for rtype, rname in [key.split("/", 1)]
            if rtype == "container"
        }
        destroy_plan = _build_destroy_plan(state, destroy_deps)
        result = execute_plan(destroy_plan, store, spec.project, None, client)

        assert not result.failed
        with pytest.raises(docker.errors.NotFound):
            client.containers.get("web")
    finally:
        # Cleanup even if test fails mid-apply
        try:
            c = client.containers.get("web")
            c.stop()
            c.remove()
        except docker.errors.NotFound:
            pass
        try:
            client.networks.get("single-net").remove()
        except docker.errors.NotFound:
            pass
