# Documentation guide

This documentation defines the planning baseline for Workflow Reuse Orchestrator.
It describes the target system and the work needed to reach it. Unless explicitly
marked **implemented**, behavior is planned. The implementation remains a starter
scaffold with offline configuration inspection.

## Reading order and ownership

| Order | Document | Owns |
| --- | --- | --- |
| 1 | [Research plan](research_plan.md) | Purpose, research questions, scope, and intended contribution. |
| 2 | [Architecture](architecture.md) | Boundaries, contracts, execution flow, storage, and releases. |
| 3 | [Data](data.md) | Sources, preparation, grouping, scientific roles, and input isolation. |
| 4 | [Methods](methods.md) | Workflow construction, comparison policies, features, and fitting. |
| 5 | [Evaluation](evaluation.md) | Measurement, experiment families, statistical rules, and analysis. |
| 6 | [Implementation plan](implementation_plan.md) | Dependencies, acceptance criteria, and notebook deliverables. |
| 7 | [Decisions](decisions.md) | Open settings, resolution gates, risks, and change control. |
| Reference | [Project structure](project_structure.md) | Existing paths and intended module ownership. |
| Reference | [Operations](operations.md) | Commands that work in the current implementation. |

## Planning conventions

- **Implemented:** present in executable code and checked at the stated scope.
- **Baseline:** the design to implement and compare; it is not a completed feature
  or evidence of scientific benefit.
- **Pilot decision:** a value to resolve from development measurements before the
  stage that depends on it.
- **Frozen:** recorded with immutable inputs, versions, and checksums; later changes
  require a new release and an explicit protocol deviation where applicable.

A baseline choice can be revised with a dated reason and an assessment of the
impact on comparisons. Do not treat a draft configuration or an empty file as an
implemented method. Do not present pilot outcomes as final results.

## Configuration ownership

`configs/study.yaml` owns active methods and runtime bindings;
`configs/datasets.yaml` owns releases and partitions;
`configs/learning.yaml` owns features, fitting, calibration, and selection;
`configs/evaluation.yaml` owns scoring and the protected experimental protocol.
Prompt text belongs in `configs/prompts/`.

Documentation explains the choices. Configurations hold their executable values.
Generated manifests record the resolved values and hashes. Each setting has one
authoritative editable owner. Draft `null` values remain unresolved until the
corresponding decision gate is passed.

Update the owning document and README status when a work package passes its
acceptance criteria. Keep commands in operations aligned with the actual CLI.
