# Environment setup

Use PowerShell from the current `workflow-reuse-orchestrator` project root.
The project selects Python 3.12 through `.python-version`.

## Existing local repository

```powershell
uv sync --locked --group dev
uv run --locked orchestrator pipeline check
uv run --locked orchestrator pipeline plan
uv run --locked --group dev ruff check .
uv run --locked --group dev ruff format --check .
uv run --locked --group dev mypy src
uv run --locked --group dev pytest -q
```

The check reports `foundations_ready` and `workflow_execution_available: false`.
The five unbound runtime settings are expected until representative development
pilots establish the final values. Code checks and tests run offline.

## Fresh machine

Clone the current repository into a new folder, then install and run the same
checks above:

```powershell
git clone https://github.com/AngeloOttendorfer02/workflow-reuse-orchestrator.git
Set-Location workflow-reuse-orchestrator
uv sync --locked --group dev
```

Ollama is required only for the model metadata commands and live infrastructure
pilot. See `docs/operations.md` for those commands. Keep the previous allocation
repository and structure backups separate from the active project.