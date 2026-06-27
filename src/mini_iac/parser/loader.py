import os
import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from mini_iac.exceptions import ConfigError
from mini_iac.parser.schema import AppSpec

_VAR = re.compile(r"\$\{([^}]+)\}")


def _load_dotenv(spec_dir: Path) -> dict[str, str]:
    env_file = spec_dir / ".env"
    if not env_file.exists():
        return {}
    result: dict[str, str] = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _interp(value: str, env: dict[str, str]) -> str:
    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name not in env:
            raise ConfigError(f"Undefined variable: ${{{name}}}")
        return env[name]

    return _VAR.sub(sub, value)


def _interp_obj(obj: object, env: dict[str, str]) -> object:
    if isinstance(obj, str):
        return _interp(obj, env)
    if isinstance(obj, dict):
        return {k: _interp_obj(v, env) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_interp_obj(i, env) for i in obj]
    return obj


def _check_circular(containers: list) -> None:
    graph = {
        c["name"]: c.get("depends_on", [])
        for c in containers
        if isinstance(c, dict) and "name" in c
    }
    visited: set[str] = set()
    path: list[str] = []

    def dfs(node: str) -> None:
        if node in path:
            raise ConfigError(
                f"Circular dependency: {' -> '.join(path + [node])}"
            )
        if node in visited:
            return
        visited.add(node)
        path.append(node)
        for dep in graph.get(node, []):
            dfs(dep)
        path.pop()

    for node in graph:
        dfs(node)


def load_spec(path: Path) -> AppSpec:
    env: dict[str, str] = {**_load_dotenv(path.parent), **os.environ}
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ConfigError("Spec file must be a YAML mapping")

    try:
        raw = _interp_obj(raw, env)
    except ConfigError as e:
        raise ConfigError(
            f"{e}\n  (Looked for .env file at: {path.parent / '.env'})"
        ) from e
    containers_raw = raw.get("containers", []) or []
    _check_circular(containers_raw)

    names = [
        c["name"]
        for c in containers_raw
        if isinstance(c, dict) and "name" in c
    ]
    for name in names:
        if names.count(name) > 1:
            raise ConfigError(f"Duplicate container name: '{name}'")

    try:
        spec = AppSpec(**raw)
    except ValidationError as e:
        msgs = [
            f"  {'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
            for err in e.errors()
        ]
        raise ConfigError("Validation failed:\n" + "\n".join(msgs)) from e

    if not spec.project:
        spec = spec.model_copy(update={"project": path.stem})

    return spec
