from datetime import datetime, timezone

from mini_iac.parser.schema import AppSpec, ContainerSpec, NetworkSpec
from mini_iac.planner.diff import (
    Action, ActionType, ResourceType,
    compute_diff, container_to_dict, spec_hash,
)
from mini_iac.state.models import ResourceRecord, State


def _make_record(name: str, rtype: str, d: dict) -> ResourceRecord:
    return ResourceRecord(
        id="abc",
        name=name,
        resource_type=rtype,
        spec_hash=spec_hash(d),
        spec_dict=d,
        created_at=datetime.now(timezone.utc),
    )


def _state_with(*records: tuple[str, ResourceRecord]) -> State:
    return State(project="test", resources=dict(records))


def _spec(containers=None, network=None, volumes=None) -> AppSpec:
    return AppSpec(
        project="test",
        containers=containers or [],
        network=NetworkSpec(name=network) if network else None,
        volumes=volumes or [],
    )


def test_all_create_when_state_empty():
    desired = _spec(
        containers=[ContainerSpec(name="web", image="nginx:1.27")],
        network="app-net",
        volumes=["pg-data"],
    )
    actions = compute_diff(desired, State())
    action_map = {(a.resource_type, a.resource_name): a for a in actions}
    assert action_map[(ResourceType.CONTAINER, "web")].action_type == ActionType.CREATE
    assert action_map[(ResourceType.NETWORK, "app-net")].action_type == ActionType.CREATE
    assert action_map[(ResourceType.VOLUME, "pg-data")].action_type == ActionType.CREATE


def test_all_noop_when_state_matches():
    c = ContainerSpec(name="web", image="nginx:1.27")
    d = container_to_dict(c)
    net_d = {"name": "app-net"}
    vol_d = {"name": "pg-data"}
    state = _state_with(
        ("container/web", _make_record("web", "container", d)),
        ("network/app-net", _make_record("app-net", "network", net_d)),
        ("volume/pg-data", _make_record("pg-data", "volume", vol_d)),
    )
    desired = _spec(containers=[c], network="app-net", volumes=["pg-data"])
    actions = compute_diff(desired, state)
    assert all(a.action_type == ActionType.NOOP for a in actions)


def test_update_when_image_changes():
    old_d = container_to_dict(ContainerSpec(name="web", image="nginx:1.26"))
    state = _state_with(("container/web", _make_record("web", "container", old_d)))
    desired = _spec(containers=[ContainerSpec(name="web", image="nginx:1.27")])
    actions = compute_diff(desired, state)
    web_action = next(a for a in actions if a.resource_name == "web")
    assert web_action.action_type == ActionType.UPDATE
    assert "image" in web_action.reason


def test_update_when_env_changes():
    old_d = container_to_dict(ContainerSpec(name="web", image="nginx:1.27", env={"K": "v1"}))
    state = _state_with(("container/web", _make_record("web", "container", old_d)))
    desired = _spec(containers=[ContainerSpec(name="web", image="nginx:1.27", env={"K": "v2"})])
    actions = compute_diff(desired, state)
    web_action = next(a for a in actions if a.resource_name == "web")
    assert web_action.action_type == ActionType.UPDATE


def test_update_when_port_changes():
    old_d = container_to_dict(ContainerSpec(name="web", image="nginx:1.27", ports=["8080:80"]))
    state = _state_with(("container/web", _make_record("web", "container", old_d)))
    desired = _spec(containers=[ContainerSpec(name="web", image="nginx:1.27", ports=["9090:80"])])
    actions = compute_diff(desired, state)
    web_action = next(a for a in actions if a.resource_name == "web")
    assert web_action.action_type == ActionType.UPDATE


def test_destroy_when_not_in_desired():
    d = container_to_dict(ContainerSpec(name="old", image="nginx:1.27"))
    state = _state_with(("container/old", _make_record("old", "container", d)))
    desired = _spec()
    actions = compute_diff(desired, state)
    old_action = next(a for a in actions if a.resource_name == "old")
    assert old_action.action_type == ActionType.DESTROY


def test_mixed_plan():
    existing_d = container_to_dict(ContainerSpec(name="db", image="postgres:16"))
    state = _state_with(
        ("container/db", _make_record("db", "container", existing_d)),
        ("container/old", _make_record("old", "container", {"name": "old", "image": "x", "ports": [], "env": {}, "volumes": [], "health_check": None})),
    )
    desired = _spec(containers=[
        ContainerSpec(name="db", image="postgres:16"),   # NOOP
        ContainerSpec(name="api", image="nginx:1.27"),  # CREATE
    ])
    actions = compute_diff(desired, state)
    action_map = {a.resource_name: a for a in actions}
    assert action_map["db"].action_type == ActionType.NOOP
    assert action_map["api"].action_type == ActionType.CREATE
    assert action_map["old"].action_type == ActionType.DESTROY


def test_update_reason_when_spec_dict_is_none():
    """_diff_reason falls back to generic message when current spec_dict is None."""
    from mini_iac.planner.diff import _diff_reason
    record = _make_record("web", "container", {"name": "web", "image": "nginx:1.27", "ports": [], "env": {}, "volumes": [], "health_check": None})
    record = record.model_copy(update={"spec_dict": None})
    reason = _diff_reason({"name": "web", "image": "nginx:1.28"}, record)
    assert reason == "configuration changed"
