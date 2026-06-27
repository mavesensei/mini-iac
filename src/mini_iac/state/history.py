# src/mini_iac/state/history.py
import re
from pathlib import Path

from mini_iac.state.models import State
from mini_iac.parser.schema import AppSpec, ContainerSpec, NetworkSpec

_VERSION_RE = re.compile(r"\.v(\d+)\.json$")


def _snapshot_path(state_file: Path, n: int) -> Path:
    stem = state_file.stem  # e.g. ".iac-state" without extension
    return state_file.parent / f"{stem}.v{n}.json"


def save_snapshot(state_file: Path) -> None:
    """Copy the current state file to a versioned snapshot."""
    if not state_file.exists():
        return
    existing = list_snapshots(state_file)
    next_n = max(existing, default=0) + 1
    snapshot = _snapshot_path(state_file, next_n)
    snapshot.write_text(state_file.read_text())


def list_snapshots(state_file: Path) -> list[int]:
    """Return sorted list of snapshot version numbers found in the state file's directory."""
    pattern = state_file.stem
    versions = []
    for f in state_file.parent.glob(f"{pattern}.v*.json"):
        m = _VERSION_RE.search(f.name)
        if m:
            versions.append(int(m.group(1)))
    return sorted(versions)


def load_snapshot(n: int, state_file: Path) -> State:
    """Load snapshot version n; raises StateError if not found."""
    path = _snapshot_path(state_file, n)
    if not path.exists():
        from mini_iac.exceptions import StateError
        raise StateError(f"Snapshot v{n} not found at {path}")
    return State.model_validate_json(path.read_text())

def state_to_spec(state) -> AppSpec:
    container_names = {r.name for k, r in state.resources.items() if k.startswith("container/")}
    network_names = {r.name for k, r in state.resources.items() if k.startswith("network/")}
    volume_names = {r.name for k, r in state.resources.items() if k.startswith("volume/")}

    containers = []
    for key, record in state.resources.items():
        if not key.startswith("container/"):
            continue
        raw_deps = record.depends_on or []
        # Keep only explicit container-to-container deps; drop implicit network/volume entries
        explicit_deps = [d for d in raw_deps if d in container_names]
        containers.append(ContainerSpec(
            name=record.spec_dict["name"],
            image=record.spec_dict["image"],
            ports=record.spec_dict.get("ports", []),
            env=record.spec_dict.get("env", {}),
            depends_on=explicit_deps,
            volumes=record.spec_dict.get("volumes", []),
            health_check=record.spec_dict.get("health_check"),
        ))

    network = None
    for key, record in state.resources.items():
        if key.startswith("network/"):
            network = NetworkSpec(name=record.name)
            break  # single network per project, per current schema

    return AppSpec(
        project=state.project,
        containers=containers,
        network=network,
        volumes=list(volume_names),
    )