import threading
from unittest.mock import MagicMock, patch

import pytest

from mini_iac.executor.runner import execute_plan
from mini_iac.planner.diff import Plan, Action, ActionType, ResourceType
from mini_iac.state.store import StateStore


def test_same_batch_runs_in_parallel(tmp_path):
    barrier = threading.Barrier(2, timeout=5)

    def fake_create_container(spec, project, network, client):
        barrier.wait()  # both threads must arrive together
        return "abc"

    store = StateStore(tmp_path / "state.json")

    actions = [
        Action(ResourceType.CONTAINER, "a", ActionType.CREATE, "create",
               desired={"name": "a", "image": "nginx", "ports": [], "env": {},
                        "volumes": [], "health_check": None}, current=None),
        Action(ResourceType.CONTAINER, "b", ActionType.CREATE, "create",
               desired={"name": "b", "image": "nginx", "ports": [], "env": {},
                        "volumes": [], "health_check": None}, current=None),
    ]
    plan = Plan(actions=actions, batches=[["a", "b"]])

    with patch("mini_iac.executor.runner.cops.create_container", side_effect=fake_create_container):
        result = execute_plan(plan, store, "test", "net", MagicMock())

    assert set(result.succeeded) == {"a", "b"}
    assert result.failed == []


def test_batches_are_sequential(tmp_path):
    order = []
    lock = threading.Lock()

    def fake_create(spec, project, network, client):
        with lock:
            order.append(spec.name)
        return "x"

    store = StateStore(tmp_path / "state.json")
    actions = [
        Action(ResourceType.CONTAINER, "db", ActionType.CREATE, "create",
               desired={"name": "db", "image": "pg", "ports": [], "env": {},
                        "volumes": [], "health_check": None}, current=None),
        Action(ResourceType.CONTAINER, "api", ActionType.CREATE, "create",
               desired={"name": "api", "image": "nginx", "ports": [], "env": {},
                        "volumes": [], "health_check": None}, current=None),
    ]
    plan = Plan(actions=actions, batches=[["db"], ["api"]])

    with patch("mini_iac.executor.runner.cops.create_container", side_effect=fake_create):
        execute_plan(plan, store, "test", "net", MagicMock())

    assert order.index("db") < order.index("api")


def test_batch_failure_skips_subsequent(tmp_path):
    store = StateStore(tmp_path / "state.json")
    actions = [
        Action(ResourceType.CONTAINER, "a", ActionType.CREATE, "create",
               desired={"name": "a", "image": "nginx", "ports": [], "env": {},
                        "volumes": [], "health_check": None}, current=None),
        Action(ResourceType.CONTAINER, "b", ActionType.CREATE, "create",
               desired={"name": "b", "image": "nginx", "ports": [], "env": {},
                        "volumes": [], "health_check": None}, current=None),
    ]
    plan = Plan(actions=actions, batches=[["a"], ["b"]])

    def fail_on_a(spec, project, network, client):
        if spec.name == "a":
            raise RuntimeError("container failed")
        return "x"

    with patch("mini_iac.executor.runner.cops.create_container", side_effect=fail_on_a):
        result = execute_plan(plan, store, "test", "net", MagicMock())

    assert "a" in result.failed
    assert "b" in result.skipped
    assert result.succeeded == []


def test_noop_actions_not_executed(tmp_path):
    store = StateStore(tmp_path / "state.json")
    actions = [
        Action(ResourceType.CONTAINER, "a", ActionType.NOOP, "no change",
               desired=None, current=None),
    ]
    plan = Plan(actions=actions, batches=[])  # NOOPs filtered from batches

    with patch("mini_iac.executor.runner.cops.create_container") as mock_create:
        result = execute_plan(plan, store, "test", "net", MagicMock())
        mock_create.assert_not_called()

    assert result.succeeded == []
    assert result.failed == []
