# Workflow Reuse Orchestrator

**Task-Adaptive Multi-Agent Reasoning: Workflow Reuse for Reliable and Efficient Problem Solving**  
Master thesis project · Angelo Ottendorfer · Planning baseline: October 2026

Workflow Reuse Orchestrator is a planned local research application for answering
questions over supplied passages and tables. It studies whether a system can reuse
validated multi-agent procedures instead of planning a new collaboration for every
question, while preserving answer correctness and reducing inference work.

The system will retrieve candidate workflows, estimate their probability of success,
and execute an eligible procedure with fresh evidence from the current question.
When reuse is unsuitable or a permitted execution check fails, it can plan one
fallback workflow within the original request budget.

## Research objective

Across HotpotQA distractor, DROP, and FinQA, how much can success-prediction-based
workflow reuse reduce total token consumption and end-to-end latency relative to
fresh per-question planning, while keeping dataset-specific answer correctness
within a predefined acceptable loss margin?

The study will report paired effects and uncertainty per dataset. Library creation
and selector training are included in a separate startup-cost and request-volume
analysis, so a cheaper individual request is not mistaken for a cheaper system.

## Planned comparison

| Method | Question-time behavior |
| --- | --- |
| Single agent | One agent answers using the permitted evidence and tools. |
| Fixed workflow | Every question follows one development-selected collaboration graph. |
| Per-question planning | A coordinator creates a fresh graph for each question. |
| Similarity reuse | Select a reusable graph using a frozen similarity rule. |
| Success-prediction reuse | Predict candidate success, then choose the least token-expensive qualifying graph. |

All methods share one bound generative model, supplied evidence, tool permissions,
answer contract, and whole-request limits. Logistic regression, gradient-boosted
trees, and a two-hidden-layer MLP are planned success-predictor comparisons. The
current study configuration names the MLP as the principal learned policy; its
advantage over the simpler predictors remains a question for the experiment.

## Target system

- Four roles: coordinator, retrieval, reasoning, and checking.
- Validated directed acyclic workflow graphs with at most 12 nodes.
- A generalized, independently validated workflow library.
- A frozen text encoder and a versioned 140-feature candidate-success interface.
- One executor with cumulative accounting for planning, repair, reuse, and fallback.
- Separate development stages and immutable final-evaluation releases.
- Compact results: SQLite records, a metrics CSV, and an HTML report.
- Nine notebooks that explain and inspect the same package implementation.

The prototype is a local Python application with CLI and notebook entry points.
External web retrieval, multi-model routing, online learning during final evaluation,
and a hosted multi-user platform are outside the core scope.

## Current implementation status

The repository is a **starter scaffold**, not an executable workflow experiment.

| Area | Verified state in the supplied code |
| --- | --- |
| Package, CLI, configuration loader | Implemented. |
| Offline `pipeline check` and `pipeline plan` | Implemented. |
| Configuration and CLI tests | Implemented. |
| Dataset, runtime, workflow, learning, scoring, storage, reporting modules | Placeholders; implementation pending. |
| Nine notebooks | Narrative outlines; execution and measured figures pending. |
| Dataset/model bindings and experimental settings | Draft declarations; several values are `null`. |

A successful configuration check means `scaffold_ready`. It reports
`workflow_execution_available: false`; it does not certify model availability,
data separation, scorer validity, or final-study readiness.

## Start here

From the repository root, with Python 3.12 and uv:

```powershell
uv sync --locked --group dev
uv run --locked orchestrator pipeline check --config configs/study.yaml
uv run --locked orchestrator pipeline plan --config configs/study.yaml
```

These commands are offline and require neither Ollama nor downloaded datasets.
See [operations](docs/operations.md) for supported commands and development checks.
There is currently no command that executes the planned study.

## Planning documentation

| Document | Contents |
| --- | --- |
| [Documentation guide](docs/README.md) | Reading order, document ownership, and planning conventions. |
| [Research plan](docs/research_plan.md) | Problem, questions, scope, hypotheses, and deliverables. |
| [Architecture](docs/architecture.md) | Components, contracts, execution, persistence, and release boundaries. |
| [Data plan](docs/data.md) | Dataset preparation, source grouping, partitions, scoring inputs, and provenance. |
| [Methods](docs/methods.md) | Baselines, library construction, features, predictors, selection, and fallback. |
| [Evaluation protocol](docs/evaluation.md) | Experiments, metrics, statistical analysis, workload, and reporting. |
| [Implementation plan](docs/implementation_plan.md) | Ordered work packages, acceptance gates, notebooks, and completion criteria. |
| [Decisions](docs/decisions.md) | Baseline choices, open values, risks, and freeze requirements. |
| [Project structure](docs/project_structure.md) | File-level implementation ownership. |

## Repository layout

| Path | Responsibility |
| --- | --- |
| `src/workflow_reuse_orchestrator/` | Shared application and research logic. |
| `configs/` | Study, dataset, learning, evaluation settings, and role prompts. |
| `tests/` | Contract, unit, integration, end-to-end, and notebook checks. |
| `notebooks/` | Sequential research narratives backed by persisted artifacts. |
| `docs/` | The planning and operating documentation. |
| `data/` | Raw releases, prepared snapshots, and recomputable caches. |
| `runs/` | Per-run records and compact reports. |
| `artifacts/` | Deliberate exports of frozen releases. |

Research logic belongs in `src/`. CLI commands and notebooks call the same
functions. Generated data, caches, model artifacts, and run outputs remain outside
Git; their identities and checksums are recorded for reproducibility.

## Development checks

```powershell
uv run --locked --group dev ruff check .
uv run --locked --group dev ruff format --check .
uv run --locked --group dev mypy src
uv run --locked --group dev pytest -q
```

At present these checks cover the configuration/CLI foundation. Empty modules and
test files do not establish coverage of future functionality. The next work is to
complete the planning gates in [the implementation plan](docs/implementation_plan.md)
before extending the executable system.
