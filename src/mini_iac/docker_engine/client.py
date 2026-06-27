# src/mini_iac/docker_engine/client.py
import docker
from mini_iac.exceptions import DaemonNotReachable

_client: docker.DockerClient | None = None


def get_docker_client() -> docker.DockerClient:
    global _client
    if _client is None:
        try:
            c = docker.from_env()
            c.ping()
            _client = c
        except docker.errors.DockerException as e:
            raise DaemonNotReachable(
                "Docker daemon not reachable — is Docker running?"
            ) from e
    return _client
