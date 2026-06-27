from graphlib import CycleError, TopologicalSorter

from mini_iac.exceptions import PlannerError
from mini_iac.planner.diff import Action, ActionType


def resolve_dependencies(
    containers: list[tuple[str, list[str], list[str]]],  # (name, explicit_depends_on, volume_names)
    network_name: str | None,
) -> dict[str, list[str]]:
    depends_on: dict[str, list[str]] = {}
    for name, explicit_deps, volumes in containers:
        deps = list(explicit_deps) + list(volumes)
        if network_name:
            deps.append(network_name)
        depends_on[name] = deps
    return depends_on

def build_batches(
    actions: list[Action],
    depends_on: dict[str, list[str]],
    is_destroy: bool = False,
) -> list[list[str]]:
    active = {a.resource_name for a in actions if a.action_type != ActionType.NOOP}
    graph = {
        name: [d for d in depends_on.get(name, []) if d in active]
        for name in active
    }
    try:
        sorter = TopologicalSorter(graph)
        sorter.prepare()
        batches: list[list[str]] = []
        while sorter.is_active():
            ready = list(sorter.get_ready())
            if ready:
                batches.append(ready)
            for node in ready:
                sorter.done(node)
    except CycleError as e:
        raise PlannerError(f"Circular dependency in execution graph: {e}") from e

    return list(reversed(batches)) if is_destroy else batches
