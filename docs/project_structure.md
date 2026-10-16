# Complete project structure

## Source package

### Package root

| File | Purpose |
| --- | --- |
| `src/workflow_reuse_orchestrator/__init__.py` | Python package initializer. |
| `src/workflow_reuse_orchestrator/cli.py` | Command-line parsing and pipeline entry point. |
| `src/workflow_reuse_orchestrator/config.py` | Typed four-document declarations, single-pass bundle loading, ownership/cross-document validation and project paths. |
| `src/workflow_reuse_orchestrator/storage.py` | Transactional SQLite receipts, artifacts, checksums, and read-only access. |

### domain

| File | Purpose |
| --- | --- |
| `src/workflow_reuse_orchestrator/domain/__init__.py` | Python package initializer. |
| `src/workflow_reuse_orchestrator/domain/tasks.py` | Questions, supplied passages/tables, source locations, and evaluator references. |
| `src/workflow_reuse_orchestrator/domain/workflows.py` | Legacy v1 graphs, v2 typed input bindings, canonical output ports and DAG validation. |
| `src/workflow_reuse_orchestrator/domain/outcomes.py` | Receipts, role outputs, fresh-evidence validation and cumulative attempt snapshots. Selection decisions/event traces remain planned. |
| `src/workflow_reuse_orchestrator/domain/budgets.py` | Request allowances and measured cumulative resource usage. |
| `src/workflow_reuse_orchestrator/domain/providers.py` | Generative model/inference contracts and typed local tool results/protocols. Encoder binding is currently declared in config.py. |

### data

| File | Purpose |
| --- | --- |
| `src/workflow_reuse_orchestrator/data/__init__.py` | Python package initializer. |
| `src/workflow_reuse_orchestrator/data/prepare.py` | Acquire sources and prepare versioned canonical dataset snapshots. |
| `src/workflow_reuse_orchestrator/data/hotpotqa.py` | HotpotQA distractor normalization and provenance. |
| `src/workflow_reuse_orchestrator/data/drop.py` | DROP passage/question/answer normalization. |
| `src/workflow_reuse_orchestrator/data/finqa.py` | FinQA report text, tables, cells, and evaluator references. |
| `src/workflow_reuse_orchestrator/data/splits.py` | Connected source groups and scientific partition assignments. |

### runtime

| File | Purpose |
| --- | --- |
| `src/workflow_reuse_orchestrator/runtime/__init__.py` | Python package initializer. |
| `src/workflow_reuse_orchestrator/runtime/ollama.py` | Verified fixed-model metadata, generation, lifecycle, and telemetry. |
| `src/workflow_reuse_orchestrator/runtime/encoder.py` | Pinned text encoding, chunking, pooling, and representation caches. |
| `src/workflow_reuse_orchestrator/runtime/tools.py` | Supplied-source search and restricted calculator execution. |
| `src/workflow_reuse_orchestrator/runtime/budgets.py` | Shared request accounting and remaining-allowance enforcement. |

### workflows

| File | Purpose |
| --- | --- |
| `src/workflow_reuse_orchestrator/workflows/__init__.py` | Python package initializer. |
| `src/workflow_reuse_orchestrator/workflows/agents.py` | Role-specific instructions, structured outputs, and tool loops. |
| `src/workflow_reuse_orchestrator/workflows/planning.py` | Coordinator planning and bounded malformed-plan repair. |
| `src/workflow_reuse_orchestrator/workflows/execution.py` | Deterministic graph execution, handoffs, evidence, and failure traces. |
| `src/workflow_reuse_orchestrator/workflows/library.py` | Discovery, generalization, validation, deduplication, and retrieval. |
| `src/workflow_reuse_orchestrator/workflows/policies.py` | The five principal policies and common reuse fallback behavior. |

### learning

| File | Purpose |
| --- | --- |
| `src/workflow_reuse_orchestrator/learning/__init__.py` | Python package initializer. |
| `src/workflow_reuse_orchestrator/learning/examples.py` | Matched task/workflow outcomes and eligible binary-success labels. |
| `src/workflow_reuse_orchestrator/learning/features.py` | The shared 140-feature contract and fitting-only transforms. |
| `src/workflow_reuse_orchestrator/learning/training.py` | LR/RF/GBT/MLP fitting and validation-based family selection, calibration, tuning, and feature ablations. |
| `src/workflow_reuse_orchestrator/learning/selection.py` | Frozen success prediction, thresholding, and token-cost selection. |

### evaluation

| File | Purpose |
| --- | --- |
| `src/workflow_reuse_orchestrator/evaluation/__init__.py` | Python package initializer. |
| `src/workflow_reuse_orchestrator/evaluation/scoring.py` | Dataset-specific answer parsing and correctness scoring. |
| `src/workflow_reuse_orchestrator/evaluation/statistics.py` | Paired comparisons, clustered intervals, correctness gates, and agreement. |

### experiments

| File | Purpose |
| --- | --- |
| `src/workflow_reuse_orchestrator/experiments/__init__.py` | Python package initializer. |
| `src/workflow_reuse_orchestrator/experiments/pipeline.py` | Stage orchestration and shared CLI/notebook execution API. |
| `src/workflow_reuse_orchestrator/experiments/stages.py` | Resumable job states, progress, and named stage work. |
| `src/workflow_reuse_orchestrator/experiments/definitions.py` | Main, transfer, ablation, volume, repetition, and diagnostic scopes. |
| `src/workflow_reuse_orchestrator/experiments/freeze.py` | Immutable release publication and protected-run verification. |

### reporting

| File | Purpose |
| --- | --- |
| `src/workflow_reuse_orchestrator/reporting/__init__.py` | Python package initializer. |
| `src/workflow_reuse_orchestrator/reporting/queries.py` | Read-only result queries and compact analytical tables. |
| `src/workflow_reuse_orchestrator/reporting/plots.py` | Shared figures for notebooks, report, and thesis exports. |
| `src/workflow_reuse_orchestrator/reporting/report.py` | HTML summaries, selected traces, and deliberate exports. |
| `src/workflow_reuse_orchestrator/reporting/templates/report.html` | HTML report template. |

## Configurations and prompts

| File | Purpose |
| --- | --- |
| `configs/study.yaml` | Active workflow study, model/runtime bindings, shared limits, and methods. |
| `configs/datasets.yaml` | Source releases, grouping, partitions, and snapshot bindings. |
| `configs/learning.yaml` | Features, predictor searches, calibration, thresholds, and cost estimates. |
| `configs/evaluation.yaml` | Scoring, final populations, statistics, repetitions, and assessment. |
| `configs/prompts/coordinator.md` | Versioned coordinator instructions. |
| `configs/prompts/retrieval.md` | Versioned retrieval instructions. |
| `configs/prompts/reasoning.md` | Versioned reasoning instructions. |
| `configs/prompts/checking.md` | Versioned checking instructions. |
| `configs/prompts/generalization.md` | Versioned generalization instructions. |

## Notebooks

| File | Purpose |
| --- | --- |
| `notebooks/01_data_overview.ipynb` | Acquire/inspect development releases and understand document-question distributions. |
| `notebooks/02_data_preparation.ipynb` | Normalize inputs, preserve sources/tables, verify scorers, and build scientific partitions. |
| `notebooks/03_agent_execution.ipynb` | Explain retrieval, reasoning, checking, graph execution, and shared budgets on development questions. |
| `notebooks/04_baselines_and_planning.ipynb` | Compare the single agent, fixed workflow, and fresh planner in a representative development pilot. |
| `notebooks/05_workflow_library.ipynb` | Discover, generalize, independently validate, and inspect reusable procedures. |
| `notebooks/06_selector_data_and_features.ipynb` | Collect matched candidate outcomes and prepare/audit the 140 features. |
| `notebooks/07_selector_training.ipynb` | Compare LR/RF/GBT/MLP, select the predictor on development validation, calibrate and select thresholds. |
| `notebooks/08_complete_pipeline.ipynb` | Run the complete adaptive prototype and all five policies on a small development population. |
| `notebooks/09_final_results.ipynb` | Analyze the frozen final study and produce thesis figures/tables. |

## Tests

| File | Purpose |
| --- | --- |
| `tests/contract/test_workflow_architecture.py` | Import boundaries and reference isolation. |
| `tests/unit/test_configuration_loading.py` | Implemented configuration/path and typed-binding failure checks. |
| `tests/unit/test_runtime_tools.py` | Implemented supplied-source search and restricted arithmetic checks. |
| `tests/conftest.py` | Offline fixtures, default network denial, strict live-test opt-in. |
| `tests/unit/test_scientific_configuration.py` | Ownership, bounds and scientific declaration failures. |
| `tests/unit/test_offline_test_mode.py` | Unmarked tests cannot open connections or resolve names. |
| `tests/integration/test_configuration_readiness.py` | Offline gate exit codes, hashes, cross-document identities and false-readiness prevention. |
| `tests/integration/test_live_runtime_metadata.py` | Optional read-only model metadata test, skipped unless explicitly enabled. |
| `tests/unit/test_document_preparation.py` | Canonical passages/tables and source provenance. |
| `tests/unit/test_source_partition_contract.py` | Connected source groups and partition isolation. |
| `tests/unit/test_workflow_graph_contract.py` | Graph validation and declared node bindings. |
| `tests/unit/test_workflow_bindings.py` | V2 port/type/dependency validation and v1 separation. |
| `tests/unit/test_runtime_budget_accounting.py` | Cumulative allowances, failures, and telemetry availability. |
| `tests/unit/test_selector_feature_contract.py` | 140-feature order, rank behavior, and transform provenance. |
| `tests/unit/test_dataset_answer_scoring.py` | Dataset-specific answer/scoring fixtures. |
| `tests/unit/test_role_agent_contract.py` | Role outputs, tools, and fresh evidence. |
| `tests/unit/test_workflow_library_contract.py` | Generalization, validation, and candidate matching. |
| `tests/unit/test_success_predictor_training.py` | Predictor fitting, calibration, and persisted parity. |
| `tests/integration/test_workflow_study_pipeline.py` | Measured stage orchestration and resume behavior. |
| `tests/integration/test_fixed_model_runtime_provider.py` | Ollama identity verification and lifecycle. |
| `tests/integration/test_workflow_result_storage.py` | Transactional receipt and artifact persistence. |
| `tests/integration/test_frozen_workflow_selector_release.py` | Release integrity and protected execution. |
| `tests/e2e/test_supplied_document_workflow.py` | Small mock end-to-end document study. |
| `tests/notebooks/test_numbered_notebook_smoke.py` | Independent notebook fixture/smoke checks. |

## Documentation and examples

| File | Purpose |
| --- | --- |
| `examples/document_question.json` | Reference-free demonstration input placeholder. |
| `examples/bound_workflow.json` | Valid v2 binding declaration; structural example, without executing agents. |
| `docs/README.md` | Documentation reading order and ownership. |
| `docs/research_plan.md` | Research questions, scope, hypotheses, and deliverables. |
| `docs/architecture.md` | Components, contracts, execution, persistence, and releases. |
| `docs/contracts.md` | Implemented binding, output, evidence, attempt and accounting semantics. |
| `docs/data.md` | Dataset sources, preparation, source groups, and partitions. |
| `docs/methods.md` | Baselines, library construction, features, training, and selection. |
| `docs/evaluation.md` | Experiment families, metrics, statistical rules, and reporting. |
| `docs/implementation_plan.md` | Work packages, acceptance criteria, and notebook deliverables. |
| `docs/commit_plan.md` | The 60-commit plan and governing academic timetable. |
| `docs/decisions.md` | Baseline decisions, unresolved settings, risks, and freeze requirements. |
| `docs/operations.md` | Commands supported by the implemented scaffold. |
| `docs/project_structure.md` | Complete file-by-file target structure overview. |

## Root files

| File | Purpose |
| --- | --- |
| `pyproject.toml` | Application/dev dependencies, tools, and the new CLI entry point. |
| `uv.lock` | Generated dependency lock for this new project. |
| `.env.example` | Example runtime environment settings. |
| `.gitignore` | Ignore generated data, caches, run outputs, environments, and local `.idea/` settings. |
| `.github/workflows/ci.yml` | Pinned Python 3.12 Linux/Windows offline check matrix; no live model or benchmark jobs. |
| `README.md` | Scope, current status, and documentation entry point. |
| `SETUP.md` | Initial PowerShell setup, checks, first commit, and GitHub steps. |
| `.python-version` | Python 3.12 selection for uv. |

## Generated-data and output folders

| Folder | Purpose |
| --- | --- |
| `data/raw/` | Acquired source releases. |
| `data/processed/` | Versioned canonical dataset snapshots. |
| `data/cache/` | Recomputable representations and indexes. |
| `runs/` | Per-run SQLite results, metrics CSV, and HTML report. |
| `artifacts/` | Explicit frozen-release exports. |
| `tests/fixtures/` | Small deterministic input and receipt fixtures. |
