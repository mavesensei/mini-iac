import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum

from mini_iac.parser.schema import AppSpec, ContainerSpec
from mini_iac.state.models import ResourceRecord, State


class ResourceType(StrEnum):
    CONTAINER = "container"
    NETWORK = "network"
    VOLUME = "volume"


class ActionType(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DESTROY = "destroy"
    NOOP = "noop"


@dataclass
class Action:
    resource_type: ResourceType
    resource_name: str
    action_type: ActionType
    reason: str
    desired: dict | None = None
    current: dict | None = None


@dataclass
class Plan:
    actions: list[Action]
    batches: list[list[str]] = field(default_factory=list)


def spec_hash(d: dict) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()


def container_to_dict(c: ContainerSpec) -> dict:
    return {
        "name": c.name,
        "image": c.image,
        "ports": sorted(c.ports),
        "env": dict(sorted(c.env.items())),
        "volumes": sorted(c.volumes),
        "health_check": c.health_check.model_dump() if c.health_check else None,
    }


def _diff_reason(desired_dict: dict, record: ResourceRecord) -> str:
    if not record.spec_dict:
        return "configuration changed"
    diffs = []
    for k in desired_dict:
        dv, cv = desired_dict.get(k), record.spec_dict.get(k)
        if dv != cv:
            diffs.append(f"{k} changed: {cv!r} → {dv!r}")
    return "; ".join(diffs) or "configuration changed"


def compute_diff(desired: AppSpec, current: State) -> list[Action]:
    actions: list[Action] = []
    desired_keys: set[str] = set()

    if desired.network:
        key = f"network/{desired.network.name}"
        desired_keys.add(key)
        d = {"name": desired.network.name}
        if key not in current.resources:
            actions.append(Action(ResourceType.NETWORK, desired.network.name, ActionType.CREATE, "does not exist", desired=d))
        else:
            actions.append(Action(ResourceType.NETWORK, desired.network.name, ActionType.NOOP, "no changes"))

    for vol in desired.volumes:
        key = f"volume/{vol}"
        desired_keys.add(key)
        d = {"name": vol}
        if key not in current.resources:
            actions.append(Action(ResourceType.VOLUME, vol, ActionType.CREATE, "does not exist", desired=d))
        else:
            actions.append(Action(ResourceType.VOLUME, vol, ActionType.NOOP, "no changes"))

    for c in desired.containers:
        key = f"container/{c.name}"
        desired_keys.add(key)
        d = container_to_dict(c)
        h = spec_hash(d)
        if key not in current.resources:
            actions.append(Action(ResourceType.CONTAINER, c.name, ActionType.CREATE, "does not exist", desired=d))
        elif current.resources[key].spec_hash != h:
            reason = _diff_reason(d, current.resources[key])
            actions.append(Action(ResourceType.CONTAINER, c.name, ActionType.UPDATE, reason, desired=d, current=current.resources[key].spec_dict))
        else:
            actions.append(Action(ResourceType.CONTAINER, c.name, ActionType.NOOP, "no changes"))

    for key, record in current.resources.items():
        if key not in desired_keys:
            rtype, rname = key.split("/", 1)
            actions.append(Action(ResourceType(rtype), rname, ActionType.DESTROY, "not in desired state", current=record.spec_dict))

    return actions
