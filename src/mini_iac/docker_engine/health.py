# src/mini_iac/docker_engine/health.py
import time
import urllib.request
import urllib.error

from mini_iac.exceptions import HealthCheckFailedError
from mini_iac.parser.schema import HealthCheckSpec


def wait_for_healthy(spec: HealthCheckSpec) -> None:
    url = f"http://localhost:{spec.port}{spec.path}"
    last_error: Exception | None = None

    for attempt in range(1, spec.retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if 200 <= resp.status < 300:
                    return
                last_error = Exception(f"HTTP {resp.status}")
        except Exception as e:
            last_error = e

        if attempt < spec.retries:
            time.sleep(spec.interval_seconds)

    raise HealthCheckFailedError(
        f"Health check failed after {spec.retries} attempts at {url}",
        last_error=last_error,
        attempts=spec.retries,
    )
