# src/mini_iac/state/store.py
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from mini_iac.exceptions import StateError
from mini_iac.state.models import State


class StateStore:
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self._lock_file = state_file.with_suffix(".lock")
        self._tmp_file = state_file.with_suffix(".tmp")

    def load(self) -> State:
        if not self.state_file.exists():
            return State()
        return State.model_validate_json(self.state_file.read_text())

    def save(self, state: State) -> None:
        self._tmp_file.write_text(state.model_dump_json(indent=2))
        os.replace(self._tmp_file, self.state_file)

    def lock(self) -> None:
        if self._lock_file.exists():
            data = json.loads(self._lock_file.read_text())
            pid, ts = data["pid"], data["timestamp"]
            try:
                os.kill(pid, 0)
                raise StateError(
                    f"State locked by PID {pid} since {ts} — "
                    "is another iac process running?"
                )
            except ProcessLookupError:
                self._lock_file.unlink()
            except PermissionError:
                # Process exists but owned by different user — treat as live
                raise StateError(
                    f"State locked by PID {pid} since {ts} — "
                    "is another iac process running?"
                )

        self._lock_file.write_text(
            json.dumps({"pid": os.getpid(), "timestamp": datetime.now(timezone.utc).isoformat()})
        )

    def unlock(self) -> None:
        if self._lock_file.exists():
            self._lock_file.unlink()

    @contextmanager
    def locked(self) -> Iterator[None]:
        self.lock()
        try:
            yield
        finally:
            self.unlock()
