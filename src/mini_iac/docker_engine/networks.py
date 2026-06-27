import docker

from mini_iac.exceptions import DockerError
from mini_iac.parser.schema import NetworkSpec


def create_network(spec: NetworkSpec, project: str, client: docker.DockerClient) -> str:
    labels = {
        "mini-iac.managed": "true",
        "mini-iac.project": project,
        "mini-iac.resource": spec.name,
    }
    try:
        network = client.networks.create(spec.name, labels=labels)
        return network.id
    except docker.errors.APIError as e:
        raise DockerError(f"Failed to create network '{spec.name}': {e}") from e


def remove_network(name: str, client: docker.DockerClient) -> None:
    try:
        network = client.networks.get(name)
        network.remove()
    except docker.errors.NotFound:
        pass
    except docker.errors.APIError as e:
        raise DockerError(f"Failed to remove network '{name}': {e}") from e
