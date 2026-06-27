# src/mini_iac/docker_engine/containers.py
import docker

from mini_iac.exceptions import ContainerNotFoundError, DockerError, ImagePullError
from mini_iac.parser.schema import ContainerSpec

_MANAGED_LABELS = {"mini-iac.managed": "true"}


def _parse_ports(ports: list[str]) -> dict:
    result: dict = {}
    for p in ports:
        if ":" in p:
            host_port, container_port = p.split(":", 1)
            result[f"{container_port}/tcp"] = int(host_port)
        else:
            result[f"{p}/tcp"] = None
    return result


def _parse_volumes(volumes: list[str]) -> dict:
    result: dict = {}
    for v in volumes:
        if ":" in v:
            src, target = v.split(":", 1)
            result[src] = {"bind": target, "mode": "rw"}
    return result


def create_container(
    spec: ContainerSpec,
    project: str,
    network_name: str | None,
    client: docker.DockerClient,
) -> str:
    labels = {
        **_MANAGED_LABELS,
        "mini-iac.project": project,
        "mini-iac.resource": spec.name,
    }
    try:
        container = client.containers.run(
            spec.image,
            name=spec.name,
            detach=True,
            ports=_parse_ports(spec.ports),
            environment=spec.env,
            labels=labels,
            volumes=_parse_volumes(spec.volumes),
            network=network_name,
        )
        return container.id
    except docker.errors.ImageNotFound as e:
        raise ImagePullError(f"Image not found: {spec.image}") from e
    except docker.errors.APIError as e:
        raise DockerError(f"Failed to create container '{spec.name}': {e}") from e


def remove_container(name: str, client: docker.DockerClient) -> None:
    try:
        container = client.containers.get(name)
        container.stop(timeout=10)
        container.remove()
    except docker.errors.NotFound as e:
        raise ContainerNotFoundError(f"Container '{name}' not found") from e
    except docker.errors.APIError as e:
        raise DockerError(f"Failed to remove container '{name}': {e}") from e


def inspect_container(name: str, client: docker.DockerClient) -> dict:
    try:
        container = client.containers.get(name)
        return container.attrs
    except docker.errors.NotFound as e:
        raise ContainerNotFoundError(f"Container '{name}' not found") from e
    except docker.errors.APIError as e:
        raise DockerError(f"Failed to inspect container '{name}': {e}") from e

def container_spec_dict_from_live(container) -> dict:
    """Reconstruct a spec-like dict from a live Docker container object.
    Used by refresh_state to adopt containers that exist in Docker but are
    missing from the state file (e.g. after a crash mid-apply)."""
    attrs = container.attrs
    image_tags = attrs.get("Config", {}).get("Image", "")

    ports = []
    port_bindings = attrs.get("HostConfig", {}).get("PortBindings") or {}
    for container_port, bindings in port_bindings.items():
        if not bindings:
            continue
        host_port = bindings[0].get("HostPort")
        proto_stripped = container_port.split("/")[0]
        if host_port:
            ports.append(f"{host_port}:{proto_stripped}")

    volumes = []
    for mount in attrs.get("Mounts", []):
        if mount.get("Type") == "volume":
            name = mount.get("Name")
            dest = mount.get("Destination")
            if name and dest:
                volumes.append(f"{name}:{dest}")

    env_list = attrs.get("Config", {}).get("Env", []) or []
    env = {}
    for item in env_list:
        if "=" in item:
            k, v = item.split("=", 1)
            env[k] = v

    return {
        "name": container.name.lstrip("/"),
        "image": image_tags,
        "ports": sorted(ports),
        "env": dict(sorted(env.items())),
        "volumes": sorted(volumes),
        "health_check": None,  # cannot be reconstructed from live Docker state
    }