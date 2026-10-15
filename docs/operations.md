# Operations and current capabilities

Run commands from the project root with Python 3.12 and uv. Only the commands
below are currently implemented. Dataset preparation, model verification, workflow
execution, training, freezing, final evaluation, and report generation are planned.
See the [implementation plan](implementation_plan.md) for their acceptance gates.

## Install the locked environment

```powershell
uv sync --locked --group dev
```

The lock includes the application and development tools. Notebook plotting and
runtime dependencies will be added with the work packages that use them.

## Inspect the starter study

```powershell
uv run --locked orchestrator --help
uv run --locked orchestrator --version
uv run --locked orchestrator pipeline check --config configs/study.yaml
uv run --locked orchestrator pipeline plan --config configs/study.yaml
```

Both pipeline commands are offline. A successful check reports
`status: scaffold_ready` and `workflow_execution_available: false`. The model,
encoder, inference, prompts, and request-limit bindings are initially pending.
This is the current scaffold state. The linked configuration files contain
draft declarations; their full scientific schemas belong to later work packages.

The plan lists the nine intended stages with `status: pending`. No stage can
execute yet. Runtime-check, preparation, training, freeze, and final-evaluation
commands will be added when their implementation is available.

## Verify a change

```powershell
uv run --locked --group dev ruff check .
uv run --locked --group dev ruff format --check .
uv run --locked --group dev mypy src
uv run --locked --group dev pytest -q
```

Stop if a command fails and resolve the reported issue before committing.
These checks currently cover the implemented configuration and CLI foundation;
empty test files do not establish coverage of future functionality.

For routine formatting and automatic lint fixes:

```powershell
uv run --locked --group dev ruff check . --fix
uv run --locked --group dev ruff format .
```

Review the changed files and repeat the verification commands after applying
fixes. Dataset acquisition, model calls, fitting, and generated outputs remain
explicit later operations.

## Planned operational behavior

Future stage commands will require explicit run/snapshot/release identities and
scientific scope. Final execution must verify an immutable release and cannot fit
predictors, tune thresholds, or update a library. Resume must preserve completed
records and distinguish unknown external effects from safe-to-run jobs.

Long stages will display stage/subphase, scope/fold, method/task/role,
completed/failed/unknown counts, elapsed time, and available usage. The report will
provide compact summaries and selected trace inspection from SQLite records. These
are target requirements; command syntax will be documented when implemented.
