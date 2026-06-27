# tests/unit/test_docker_containers.py
from unittest.mock import MagicMock
import pytest
import docker.errors

from mini_iac.docker_engine.containers import create_container, remove_container, inspect_container
from mini_iac.exceptions import ContainerNotFoundError, DockerError, ImagePullError
from mini_iac.parser.schema import ContainerSpec


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def simple_spec():
    return ContainerSpec(name="web", image="nginx:1.27", ports=["8080:80"])


def test_create_container_returns_id(mock_client, simple_spec):
    mock_client.containers.run.return_value.id = "abc123"
    result = create_container(simple_spec, "myproject", "my-net", mock_client)
    assert result == "abc123"
    mock_client.containers.run.assert_called_once()
    call_kwargs = mock_client.containers.run.call_args[1]
    assert call_kwargs["name"] == "web"
    assert call_kwargs["labels"]["mini-iac.managed"] == "true"
    assert call_kwargs["labels"]["mini-iac.project"] == "myproject"


def test_create_container_port_mapping(mock_client, simple_spec):
    mock_client.containers.run.return_value.id = "abc123"
    create_container(simple_spec, "myproject", None, mock_client)
    call_kwargs = mock_client.containers.run.call_args[1]
    assert call_kwargs["ports"] == {"80/tcp": 8080}


def test_create_container_volume_mapping(mock_client, simple_spec):
    spec = ContainerSpec(name="db", image="postgres:16", volumes=["pg-data:/var/lib/postgresql/data"])
    mock_client.containers.run.return_value.id = "abc123"
    create_container(spec, "myproject", None, mock_client)
    call_kwargs = mock_client.containers.run.call_args[1]
    assert call_kwargs["volumes"] == {"pg-data": {"bind": "/var/lib/postgresql/data", "mode": "rw"}}


def test_create_container_image_not_found_raises(mock_client, simple_spec):
    mock_client.containers.run.side_effect = docker.errors.ImageNotFound("not found")
    with pytest.raises(ImagePullError, match="nginx:1.27"):
        create_container(simple_spec, "myproject", None, mock_client)


def test_remove_container_stops_and_removes(mock_client):
    mock_container = MagicMock()
    mock_client.containers.get.return_value = mock_container
    remove_container("web", mock_client)
    mock_container.stop.assert_called_once()
    mock_container.remove.assert_called_once()


def test_remove_container_not_found_raises(mock_client):
    mock_client.containers.get.side_effect = docker.errors.NotFound("not found")
    with pytest.raises(ContainerNotFoundError, match="web"):
        remove_container("web", mock_client)


def test_inspect_container_returns_attrs(mock_client):
    mock_client.containers.get.return_value.attrs = {"Id": "abc123", "Name": "/web"}
    result = inspect_container("web", mock_client)
    assert result["Id"] == "abc123"


def test_inspect_container_not_found_raises(mock_client):
    mock_client.containers.get.side_effect = docker.errors.NotFound("not found")
    with pytest.raises(ContainerNotFoundError, match="web"):
        inspect_container("web", mock_client)
