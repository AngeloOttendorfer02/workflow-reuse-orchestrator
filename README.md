# Workflow Reuse Orchestrator

Master thesis implementation for **Task-Adaptive Multi-Agent Reasoning: Workflow
Reuse for Reliable and Efficient Problem Solving**.

The planned study compares single-agent execution, a fixed workflow, fresh
per-question planning, similarity-based workflow reuse, and success-prediction
reuse on HotpotQA distractor, DROP, and FinQA.

## Current status

The first commit provides the fixed project structure, dependency lock,
configuration declarations, nine notebook outlines, and working offline CLI
checks. Model execution, dataset preparation, workflow reuse, predictor fitting,
plots, and final evaluation are pending implementation.

`pipeline check` validates the starter study declarations, project-relative
configuration references, and linked YAML document identities. It does not
verify model metadata, scientific partitions, feature implementations, or final
evaluation readiness. `pipeline plan` displays planned stages; it executes none.
Unimplemented modules and tests remain empty to show their agreed ownership.

## Quick start

Run these commands from the project root with Python 3.12 and uv:

```powershell
uv sync --locked --group dev
uv run --locked orchestrator pipeline check
uv run --locked orchestrator pipeline plan
```

Expected check status: `scaffold_ready`, with
`workflow_execution_available: false` and five pending runtime bindings.
Ollama and datasets are not needed for these commands.

## Project guide

- [Initial setup and first commit](SETUP.md)
- [Complete file overview](docs/project_structure.md)
- [Architecture and implementation plan](docs/architecture.md)
- [Implemented commands and development checks](docs/operations.md)

The Python package is `workflow_reuse_orchestrator`. Both the CLI and future
notebooks use this package. Research logic belongs in `src/`; notebooks explain
and inspect persisted results through package functions.

The previous allocation repository and its backups remain separate historical
sources. Reusable foundations will be adapted deliberately into this project.
