import pytest
from mini_iac.planner.diff import Action, ActionType, ResourceType
from mini_iac.planner.graph import build_batches
from mini_iac.exceptions import PlannerError


def _action(name: str, atype: ActionType = ActionType.CREATE) -> Action:
    return Action(
        resource_type=ResourceType.CONTAINER,
        resource_name=name,
        action_type=atype,
        reason="test",
    )


def test_no_deps_all_in_one_batch():
    actions = [_action("a"), _action("b"), _action("c")]
    batches = build_batches(actions, {})
    assert len(batches) == 1
    assert set(batches[0]) == {"a", "b", "c"}


def test_linear_chain_produces_ordered_batches():
    actions = [_action("a"), _action("b"), _action("c")]
    deps = {"b": ["a"], "c": ["b"]}
    batches = build_batches(actions, deps)
    # Each must come after its dependency
    flat = [name for batch in batches for name in batch]
    assert flat.index("a") < flat.index("b")
    assert flat.index("b") < flat.index("c")


def test_diamond_dependency():
    # api depends on db and redis; db and redis are independent
    actions = [_action("db"), _action("redis"), _action("api")]
    deps = {"api": ["db", "redis"]}
    batches = build_batches(actions, deps)
    flat = [name for batch in batches for name in batch]
    assert flat.index("db") < flat.index("api")
    assert flat.index("redis") < flat.index("api")
    # db and redis should be in the same batch
    batch_containing_db = next(b for b in batches if "db" in b)
    assert "redis" in batch_containing_db


def test_destroy_reverses_order():
    actions = [_action("db", ActionType.DESTROY), _action("api", ActionType.DESTROY)]
    deps = {"api": ["db"]}
    batches = build_batches(actions, deps, is_destroy=True)
    flat = [name for batch in batches for name in batch]
    assert flat.index("api") < flat.index("db")


def test_noop_excluded_from_batches():
    actions = [_action("a"), _action("b", ActionType.NOOP)]
    batches = build_batches(actions, {})
    all_names = [n for b in batches for n in b]
    assert "b" not in all_names
    assert "a" in all_names


def test_circular_dependency_raises_planner_error():
    actions = [_action("a"), _action("b")]
    with pytest.raises(PlannerError):
        build_batches(actions, {"a": ["b"], "b": ["a"]})
