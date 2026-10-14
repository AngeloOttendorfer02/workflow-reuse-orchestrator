# Workflow Reuse Orchestrator

Master thesis implementation for **Task-Adaptive Multi-Agent Reasoning: Workflow
Reuse for Reliable and Efficient Problem Solving**.

The study will compare single-agent execution, a fixed workflow, fresh
per-question planning, similarity reuse, and prediction-based reuse on HotpotQA
distractor, DROP, and FinQA.

## Implementation status

Commit 02 implements the shared foundations:

- Model-facing document inputs and separate evaluator references.
- Validated workflow declarations with at most 12 nodes and deterministic ordering.
- Fixed-model fingerprints and explicit inference controls.
- Cumulative generation, tool, repair, fallback, token, and wall-time accounting.
- Bounded decimal arithmetic and immutable, checksummed SQLite records.
- Offline configuration checks, model inspection, and a single-call runtime pilot.

The package still has the agreed 44 Python modules and nine notebook outlines.
Dataset acquisition, scoring, role agents, graph execution, the reusable library,
learning, plots, and final evaluation remain pending. Empty modules and tests
show ownership; they do not establish implemented functionality.

## Install and check

```powershell
uv sync --locked --group dev
uv run --locked orchestrator pipeline check
uv run --locked orchestrator pipeline plan
```

A successful check reports `foundations_ready`, `runtime_check_available: true`,
and `workflow_execution_available: false`. Runtime bindings marked `null` remain
pending. These checks use no model server or scientific datasets.

## Inspect the actual model runtime

```powershell
uv run --locked orchestrator runtime models
uv run --locked orchestrator runtime inspect --model "EXACT_INSTALLED_MODEL_NAME"
```

Use an exact Ollama model name from the first command. The provider no longer
uses the allocation study's resource registry. The optional single-call pilot
and its output are described in [operations](docs/operations.md).

## Project guide

- [Environment setup](SETUP.md)
- [Complete file overview](docs/project_structure.md)
- [Architecture and implementation plan](docs/architecture.md)
- [Supported commands and verification](docs/operations.md)

The Python package is `workflow_reuse_orchestrator`. Research logic belongs in
`src/`; notebooks will explain and inspect persisted results through package
functions. The document example is synthetic and is not a FinQA dataset sample
or an experimental result. The previous allocation repository remains a
separate historical source.