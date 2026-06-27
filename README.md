# mini-iac

A Terraform-inspired Infrastructure-as-Code engine for Docker, written in Python.

## Why this exists

Terraform and similar IaC tools work by comparing a declared desired state
against what actually exists, then computing the minimal set of changes
needed to reconcile the two. Understanding *why* that's hard — drift
detection, dependency ordering, partial-failure recovery, idempotency — is
much clearer after building a small version of it than after only using
one. This project re-implements that core loop against the Docker Engine
API instead of a cloud provider, which keeps the scope small enough to
build solo while still hitting the same hard problems Terraform itself had
to solve.

## What this demonstrates

- **State management** — tracks provisioned resources in `.iac-state.json` with atomic writes and file locking
- **Plan/diff** — computes the delta between desired (YAML) and current (live Docker) state before making any changes
- **Dependency resolution** — topologically sorts resources by `depends_on` and parallelises independent batches
- **Idempotency** — spec hashing ensures re-applying an unchanged spec is always a no-op
- **Drift detection** — queries Docker labels to find resources removed outside the tool

## Architecture

```
YAML spec
   │
   ▼  load_spec()
Parser (Pydantic validation + ${VAR} interpolation)
   │  AppSpec
   ▼
Planner: refresh_state() + compute_diff() + build_batches()
   │  Plan (list of Actions + parallel batches)
   ▼
Executor: ThreadPoolExecutor per batch
   │  Docker SDK calls
   ▼
Docker Engine (containers / networks / volumes)
   │  incremental state writes after each resource
   ▼
State Store (.iac-state.json)
```

## Install

```bash
git clone <repo>
cd mini-iac
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Usage

```bash
# Preview changes (no mutations)
iac plan examples/single-container.yaml

# Apply changes
iac apply examples/single-container.yaml

# Destroy all tracked resources
iac destroy

# Detect drift between state and live Docker
iac refresh

# Rollback to a previous snapshot
iac rollback
iac rollback --to-version 2
```

## Example walkthrough

Using `examples/single-container.yaml`:

```yaml
containers:
  - name: web
    image: nginx:1.27
    ports:
      - "8080:80"

network:
  name: single-net
```

### Plan

```
$ iac plan examples/single-container.yaml

Plan for single-container:

  + network/single-net  (create: does not exist)
  + container/web  (create: does not exist)

2 change(s) to apply.
```

### Apply

```
$ iac apply examples/single-container.yaml

Plan for single-container:

  + network/single-net  (create: does not exist)
  + container/web  (create: does not exist)

2 change(s) to apply.

Apply these changes? [y/N]: y

Apply results:
  ✓ single-net
  ✓ web
```

### Re-apply (no-op)

```
$ iac apply examples/single-container.yaml

Nothing to apply — infrastructure is up to date.
```

### Destroy

```
$ iac destroy

Destroy plan for single-container:

  - network/single-net  (destroy)
  - container/web  (destroy)

2 resource(s) will be destroyed.
Destroy all resources? [y/N]: y
  ✓ web destroyed
  ✓ single-net destroyed
```

## Variable Interpolation

Use `${VAR}` in any string field to interpolate values from environment variables or a `.env` file.

**Important:** the `.env` file must be placed in the *same directory as the YAML spec file* being applied, not the project root. For example, running `iac apply examples/with-vars.yaml` looks for `examples/.env`, not `.env` at the repo root.

Process environment variables take precedence over `.env` file values when both define the same key. Referencing an undefined variable raises a `ConfigError` before any Docker calls are made, naming the variable and the `.env` path that was checked.

```bash
# examples/.env
DB_PASSWORD=supersecret123
```

```yaml
# examples/with-vars.yaml
containers:
  - name: db
    image: postgres:16
    env:
      POSTGRES_PASSWORD: "${DB_PASSWORD}"
```

## Running tests

```bash
# Unit tests (no Docker required)
pytest tests/unit/

# Integration tests (requires Docker daemon)
pytest -m integration -v
```

## Issues encountered & lessons learned

| Issue | Root Cause | Fix |
|-------|------------|-----|
| `iac plan <file>` treated `plan` as the file argument, ignoring the subcommand | Typer collapses single-command apps — without `@app.callback(invoke_without_command=True)` the first positional argument is consumed as the command name | Added `@app.callback(invoke_without_command=True)` to register subcommands correctly |
| `os.kill(pid, 0)` raised `PermissionError` on cross-user processes, causing stale-lock detection to fail | Only `ProcessLookupError` was caught; `PermissionError` (EPERM) is raised when the caller lacks permission to signal the target process — but the process does exist | Added `except PermissionError` alongside `except ProcessLookupError` so cross-user live PIDs are treated as alive |
| The network UPDATE branch was dead code that could never be reached | `NetworkSpec` only carries a `name` field, so the computed hash is identical for any two specs with the same name — the diff engine therefore never emits an UPDATE action for networks | Removed the dead UPDATE branch from the network executor to prevent confusion |
| Health check accepted HTTP 4xx responses as "healthy" | The condition was `resp.status < 500` instead of `200 <= resp.status < 300`, so client-error responses were silently treated as success | Corrected the condition to `200 <= resp.status < 300` |
| `iac refresh` mutated state on disk even though it is intended to be a read-only inspection command | `store.save(refreshed)` was called at the end of the refresh flow, overwriting the stored state with live-queried data | Removed the `store.save()` call — `refresh` now only prints drift without writing to disk |
| `iac destroy` failed with "network has active endpoints" when a container and its network were destroyed together | `build_batches` only modeled explicit `depends_on` edges between containers — a container's implicit dependency on the network/volumes it uses was never added to the graph, so the container and network landed in the same parallel batch and were removed concurrently | Added `resolve_dependencies()` in `planner/graph.py` to fold each container's network and volume usage into the dependency graph, used by both `apply` and `destroy`, ensuring containers are always torn down before the resources they depend on |
| Containers' state records stored only the raw YAML `depends_on` list, omitting implicit network/volume dependencies | `runner.py` wrote `spec.depends_on` directly into each `ResourceRecord`, never incorporating the resolved network/volume edges computed by `resolve_dependencies()` — leaving the persisted dependency data inconsistent with what was actually used for execution ordering | Threaded the resolved `depends_on` list through `execute_plan()` and `_apply_action()` so the value written to state matches the graph actually used to order operations |
| `iac rollback` only overwrote the local state file and never reconciled the live Docker resources, so a "successful" rollback could leave outdated infrastructure running unnoticed | The command called `store.save(target_state)` directly with no diff/execute step — it changed what the tool believed was true without changing what was actually true | Rewrote rollback to convert the snapshot into an `AppSpec` (`state_to_spec()`), then run it through the same plan → diff → execute pipeline as `apply`, so rollback now reconciles real containers, networks, and volumes instead of just rewriting the state file |
| Rolling back while a different project's spec was active could silently merge dependency graphs and wipe state for the active project's still-running resources | Snapshot versions are numbered per state file, not per project; refreshing state with the snapshot's project name caused `refresh_state` to drop the active project's resources from state entirely, since they didn't match the label filter | Added a guard in `rollback` that compares the snapshot's `project` field against the current state's `project` and refuses to proceed on a mismatch |
| Containers adopted via drift-recovery (state lost mid-apply, e.g. a crash or Ctrl+C during health check) trigger a spurious UPDATE on the next apply | Some container metadata cannot be reconstructed from live Docker state: `health_check` config is never stored by Docker itself, and image-default environment variables (e.g. nginx's `NGINX_VERSION`) appear in the live container but were never part of the original YAML spec — so the reconstructed spec_hash differs from the original | Documented as an accepted limitation rather than patched: this only affects the first `apply` after an adoption, is self-correcting (the UPDATE reconciles the spec_hash going forward), and never causes data loss — it produces one redundant container recreation, the same trade-off Terraform makes on resource import |
