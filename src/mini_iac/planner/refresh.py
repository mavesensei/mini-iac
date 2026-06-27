import docker

from mini_iac.docker_engine.containers import container_spec_dict_from_live
from mini_iac.planner.diff import spec_hash
from mini_iac.state.models import ResourceRecord, State
from datetime import datetime, timezone


def refresh_state(current: State, project: str, client: docker.DockerClient) -> State:
    """Reconcile state with live Docker resources (two-way drift detection):
    - Resources in state but no longer in Docker are removed (stale state).
    - Resources in Docker but missing from state are adopted (e.g. after a
      crash mid-apply left a resource created but never recorded).
    """
    filters = {"label": [f"mini-iac.project={project}", "mini-iac.managed=true"]}
    now = datetime.now(timezone.utc)

    live_containers = client.containers.list(all=True, filters=filters)
    live_networks = client.networks.list(filters=filters)
    live_volumes = client.volumes.list(filters=filters)

    live_keys: set[str] = set()
    for c in live_containers:
        live_keys.add(f"container/{c.name.lstrip('/')}")
    for n in live_networks:
        live_keys.add(f"network/{n.name}")
    for v in live_volumes:
        live_keys.add(f"volume/{v.name}")

    # Step 1: drop resources that are in state but no longer live (stale state)
    resources = {k: r for k, r in current.resources.items() if k in live_keys}

    # Step 2: adopt resources that are live but missing from state
    for c in live_containers:
        key = f"container/{c.name.lstrip('/')}"
        if key in resources:
            continue
        d = container_spec_dict_from_live(c)
        resources[key] = ResourceRecord(
            id=c.id,
            name=d["name"],
            resource_type="container",
            spec_hash=spec_hash(d),
            spec_dict=d,
            depends_on=[],
            docker_labels={"mini-iac.project": project},
            created_at=now,
        )

    for n in live_networks:
        key = f"network/{n.name}"
        if key in resources:
            continue
        d = {"name": n.name}
        resources[key] = ResourceRecord(
            id=n.id,
            name=n.name,
            resource_type="network",
            spec_hash=spec_hash(d),
            spec_dict=d,
            docker_labels={"mini-iac.project": project},
            created_at=now,
        )

    for v in live_volumes:
        key = f"volume/{v.name}"
        if key in resources:
            continue
        d = {"name": v.name}
        resources[key] = ResourceRecord(
            id=v.name,
            name=v.name,
            resource_type="volume",
            spec_hash=spec_hash(d),
            spec_dict=d,
            docker_labels={"mini-iac.project": project},
            created_at=now,
        )

    return current.model_copy(update={"resources": resources})