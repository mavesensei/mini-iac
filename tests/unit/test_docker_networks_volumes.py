from unittest.mock import MagicMock
import pytest
import docker.errors

from mini_iac.docker_engine.networks import create_network, remove_network
from mini_iac.docker_engine.volumes import create_volume, remove_volume
from mini_iac.exceptions import DockerError
from mini_iac.parser.schema import NetworkSpec


@pytest.fixture
def mock_client():
    return MagicMock()


def test_create_network_returns_id(mock_client):
    mock_client.networks.create.return_value.id = "net123"
    result = create_network(NetworkSpec(name="app-net"), "myproject", mock_client)
    assert result == "net123"
    call_kwargs = mock_client.networks.create.call_args[1]
    assert call_kwargs["labels"]["mini-iac.managed"] == "true"
    assert call_kwargs["labels"]["mini-iac.project"] == "myproject"


def test_remove_network_calls_remove(mock_client):
    mock_net = MagicMock()
    mock_client.networks.get.return_value = mock_net
    remove_network("app-net", mock_client)
    mock_net.remove.assert_called_once()


def test_remove_network_not_found_is_noop(mock_client):
    mock_client.networks.get.side_effect = docker.errors.NotFound("not found")
    remove_network("app-net", mock_client)  # should not raise


def test_create_volume_returns_id(mock_client):
    mock_client.volumes.create.return_value.id = "vol123"
    result = create_volume("pg-data", "myproject", mock_client)
    assert result == "vol123"
    call_kwargs = mock_client.volumes.create.call_args[1]
    assert call_kwargs["labels"]["mini-iac.managed"] == "true"


def test_remove_volume_calls_remove(mock_client):
    mock_vol = MagicMock()
    mock_client.volumes.get.return_value = mock_vol
    remove_volume("pg-data", mock_client)
    mock_vol.remove.assert_called_once()


def test_remove_volume_not_found_is_noop(mock_client):
    mock_client.volumes.get.side_effect = docker.errors.NotFound("not found")
    remove_volume("pg-data", mock_client)  # should not raise
