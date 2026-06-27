import pytest
from unittest.mock import patch, MagicMock
import urllib.error

from mini_iac.docker_engine.health import wait_for_healthy
from mini_iac.exceptions import HealthCheckFailedError
from mini_iac.parser.schema import HealthCheckSpec


@pytest.fixture
def spec():
    return HealthCheckSpec(path="/health", port=8080, retries=3, interval_seconds=0)


def test_returns_immediately_on_200(spec):
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__ = lambda s: mock_resp
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        wait_for_healthy(spec)  # should not raise


def test_raises_after_all_retries_fail(spec):
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
        with pytest.raises(HealthCheckFailedError) as exc_info:
            wait_for_healthy(spec)
        assert exc_info.value.attempts == 3


def test_retries_on_5xx(spec):
    mock_resp = MagicMock()
    mock_resp.status = 503
    mock_resp.__enter__ = lambda s: mock_resp
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(HealthCheckFailedError):
            wait_for_healthy(spec)


def test_raises_on_4xx(spec):
    """4xx responses must not be treated as healthy."""
    mock_resp = MagicMock()
    mock_resp.status = 404
    mock_resp.__enter__ = lambda s: mock_resp
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(HealthCheckFailedError):
            wait_for_healthy(spec)
