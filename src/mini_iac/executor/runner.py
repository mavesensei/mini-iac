# src/mini_iac/executor/runner.py
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone

from mini_iac.docker_engine import containers as cops
from mini_iac.docker_engine import networks as nops
from mini_iac.docker_engine import volumes as vops
from mini_iac.parser.schema import ContainerSpec, NetworkSpec
from mini_iac.planner.diff import Action, ActionType, Plan, ResourceType, spec_hash
from mini_iac.state.models import ResourceRecord
from mini_iac.state.store import StateStore


@dataclass
class ExecutionResult:
    succeeded: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: dict[str, Exception] = field(default_factory=dict)


def _apply_action(
    action: Action,
    project: str,
    network_name: str | None,
    client,
    resolved_depends_on: list[str] | None = None,
) -> ResourceRecord | None:
    now = datetime.now(timezone.utc)

    if action.action_type == ActionType.NOOP:
        return None

    # Pre-remove phase for UPDATE and DESTROY
    if action.action_type in (ActionType.DESTROY, ActionType.UPDATE):
        if action.resource_type == ResourceType.CONTAINER:
            try:
                cops.remove_container(action.resource_name, client)
            except Exception:
                pass
        elif action.resource_type == ResourceType.NETWORK:
            nops.remove_network(action.resource_name, client)
        elif action.resource_type == ResourceType.VOLUME and action.action_type == ActionType.DESTROY:
            vops.remove_volume(action.resource_name, client)
        # Volumes on UPDATE: intentionally not removed to preserve data

    if action.action_type == ActionType.DESTROY:
        return None

    d = action.desired
    labels = {"mini-iac.project": project}

    if action.resource_type == ResourceType.CONTAINER:
        spec = ContainerSpec(**d)
        docker_id = cops.create_container(spec, project, network_name, client)
        record = ResourceRecord(
            id=docker_id,
            name=action.resource_name,
            resource_type="container",
            spec_hash=spec_hash(d),
            spec_dict=d,
            depends_on=resolved_depends_on or [],
            docker_labels=labels,
            created_at=now,
        )
        if spec.health_check:
            from mini_iac.docker_engine.health import wait_for_healthy
            try:
                wait_for_healthy(spec.health_check)
            except Exception:
                try:
                    cops.remove_container(action.resource_name, client)
                except Exception:
                    pass
                raise
        return record
    elif action.resource_type == ResourceType.NETWORK:
        net_spec = NetworkSpec(name=action.resource_name)
        docker_id = nops.create_network(net_spec, project, client)
        return ResourceRecord(
            id=docker_id,
            name=action.resource_name,
            resource_type="network",
            spec_hash=spec_hash(d),
            spec_dict=d,
            docker_labels=labels,
            created_at=now,
        )
    elif action.resource_type == ResourceType.VOLUME:
        docker_id = vops.create_volume(action.resource_name, project, client)
        return ResourceRecord(
            id=docker_id,
            name=action.resource_name,
            resource_type="volume",
            spec_hash=spec_hash(d),
            spec_dict=d,
            docker_labels=labels,
            created_at=now,
        )
    return None


def execute_plan(
    plan: Plan,
    store: StateStore,
    project: str,
    network_name: str | None,
    client,
    dry_run: bool = False,
    depends_on: dict[str, list[str]] | None = None,
) -> ExecutionResult:
    result = ExecutionResult()
    state = store.load()
    state = state.model_copy(update={"project": project})
    action_map = {a.resource_name: a for a in plan.actions}

    for i, batch in enumerate(plan.batches):
        batch_actions = [action_map[name] for name in batch if name in action_map]

        if dry_run:
            result.succeeded.extend(batch)
            continue

        batch_succeeded: list[str] = []
        batch_failed_flag = False

        with ThreadPoolExecutor(max_workers=max(len(batch_actions), 1)) as executor:
            futures = {
                executor.submit(_apply_action, action, project, network_name, client, (depends_on or {}).get(action.resource_name, [])): action
                for action in batch_actions
            }
            for future in as_completed(futures):
                action = futures[future]
                key = f"{action.resource_type}/{action.resource_name}"
                try:
                    record = future.result()
                    if action.action_type == ActionType.DESTROY:
                        state.resources.pop(key, None)
                    elif record is not None:
                        state.resources[key] = record
                    store.save(state)
                    batch_succeeded.append(action.resource_name)
                except Exception as e:
                    result.failed.append(action.resource_name)
                    result.errors[action.resource_name] = e
                    batch_failed_flag = True

        if batch_failed_flag:
            # Siblings that completed in this batch are in state — mark as succeeded
            result.succeeded.extend(batch_succeeded)
            # Only subsequent batches are truly skipped
            for remaining in plan.batches[i + 1:]:
                result.skipped.extend(remaining)
            break
        else:
            result.succeeded.extend(batch_succeeded)

    return result
