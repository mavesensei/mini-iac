import docker

from mini_iac.exceptions import DockerError


def create_volume(name: str, project: str, client: docker.DockerClient) -> str:
    labels = {
        "mini-iac.managed": "true",
        "mini-iac.project": project,
        "mini-iac.resource": name,
    }
    try:
        volume = client.volumes.create(name, labels=labels)
        return volume.id
    except docker.errors.APIError as e:
        raise DockerError(f"Failed to create volume '{name}': {e}") from e


def remove_volume(name: str, client: docker.DockerClient) -> None:
    try:
        volume = client.volumes.get(name)
        volume.remove()
    except docker.errors.NotFound:
        pass
    except docker.errors.APIError as e:
        raise DockerError(f"Failed to remove volume '{name}': {e}") from e
