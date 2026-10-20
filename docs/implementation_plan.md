# Implementation plan

The project implements the baseline in reviewable work packages. C01 integrates the
shared runtime/domain/storage foundations of WP01. Full workflow execution, study
configuration and later packages remain pending.

## Work packages and acceptance gates

| Package | Work and dependencies | Complete when |
| --- | --- | --- |
| WP01 Foundations | Finalize planning; implement typed inputs/graphs/budgets/providers, model adapter, storage, tools. | Offline checks remain valid; real runtime identity is verified; transactions, accounting, and reference isolation have meaningful tests. |
| WP02 Data and scoring | Acquire pinned releases, normalize sources/tables, verify scorers, audit connected groups and assign roles. Depends on contracts/storage. | Snapshot counts/exclusions reconcile; no forbidden source overlap; scorer fixtures pass; model inputs exclude references; notebooks 01/02 inspect persisted data. |
| WP03 Agents and baselines | Implement roles, validated graph executor, cumulative limits, single-agent and fixed workflows. | Invalid graphs fail before effects; tools use current evidence; failures retain costs; representative real baseline traces exist; notebooks 03/04 begin. |
| WP04 Planning and library | Add fresh planning/repair, discovery, generalization, independent validation, canonicalization, admission, shared retrieval. | Templates contain no copied answers/evidence; changed-evidence tests pass; admitted main/transfer libraries are frozen; all discovery costs retained; notebooks 04/05 complete. |
| WP05 Candidate evidence/features | Collect matched candidate outcomes; implement named 140-feature interface and fitting-only transformations. | Candidate IDs and attempt lineage reconcile; negatives/all-zero sets retained; unknowns distinct; training and request-time feature construction agree; notebook 06 begins. |
| WP06 Selector-data audit | Audit roles, labels, duplicates, feature leakage, rank/support, calibration/threshold scope; lock fitting plan. | A checksummed training-ready population passes audits; one-class/rank limitations have declared resolutions; notebook 06 completes. |
| WP07 Predictor fitting | Compare logistic regression, random forest, gradient-boosted trees, and MLP using matched features and grouped development data; select the final family, calibrate predictions, tune thresholds/cost estimates, refit feature ablations, and build independent transfer selectors. | The declared validation rule determines the selected family; persisted and in-memory predictions agree; calibration and overhead are measured; all fitted state has permitted lineage; notebook 07 completes. |
| WP08 Integration and freeze | Integrate all five policies/fallback, required experiment scopes, statistics/report views, representative workload pilot, immutable releases. | No gold controls execution; all attempts share limits; protected mode rejects mutable/incomplete assets; workload/precision plan is feasible; notebook 08 completes. |
| WP09 Protected study | Execute registered main, transfer, ablation, volume, repetition, and human-assessment work. | Every planned job has explicit state; unknowns/completeness disclosed; releases unchanged; paired outcomes reconcile; notebook 09 begins read-only analysis. |
| WP10 Analysis and release | Compute registered effects/intervals, interpret errors, finish report/demo, reproduce notebooks/artifacts. | Numbers derive from named queries; correctness gates limit claims; independent assessment agreement is retained; clean-checkout reproduction succeeds; notebook 09 completes. |

The principal learned policy is `prediction-reuse`; its name does not prescribe
a predictor family. Logistic regression, random forest, gradient-boosted trees,
and MLP share the same candidate observations and 140-feature interface.

Model selection uses development-validation evidence under a declared rule.
The two-hidden-layer MLP is a starting candidate architecture, not a predetermined
winner. Primary feature ablations keep the selected family fixed while refitting
and retuning each feature variant. Transfer selectors use independently permitted
development data and exclude the target dataset throughout fitting and tuning.

Transfer scope is implemented with library discovery and collection, not added at
the final stage. Each held-out dataset requires its own library and fitted release.
The selector-data audit is a scientific gate; it is not a new predictive subsystem.

## Before further feature implementation

1. Review the scope and baseline decisions in [decisions](decisions.md).
2. Resolve the operational meaning of source grouping and plan its feasibility audit.
3. Specify scorer fixtures and binary-success rules before candidate labels exist.
4. Specify runtime-contract and budget behavior before agent/tool effects are added.
5. Keep numeric pilot decisions visibly unresolved until measured evidence exists.

Planning completion does not require guessing a model context size, success
threshold, sample size, or final margin. It requires knowing where each is owned,
how it will be measured, and which dependent stage it blocks.

## Notebook deliverables

Each notebook contains a question, explicit parameters/artifact identities, package
calls, measured tables/plots, and a short interpretation with limitations.

| Notebook | Required inspection |
| --- | --- |
| `01_data_overview.ipynb` | Development source/task counts, context-length tails, table/numeric characteristics, answer types, representative inputs. |
| `02_data_preparation.ipynb` | Retained/excluded counts, connected-component sizes, overlap matrix, canonicalization examples, scorer edge cases. |
| `03_agent_execution.ipynb` | Graph, role timeline, evidence references, calls/tokens, one diagnosed failure or budget case. |
| `04_baselines_and_planning.ipynb` | Matched baseline correctness/resources, planning overhead, graph examples and failure modes. |
| `05_workflow_library.ipynb` | Generalization before/after, validation support, graph distributions, admission/rejection, coverage and retrieval examples. |
| `06_selector_data_and_features.ipynb` | Label support, all-zero candidate sets, missingness, role isolation, feature distributions, effective rank. |
| `07_selector_training.ipynb` | Training and external validation curves, MCC/Brier comparisons, reliability, threshold/coverage/error behavior. |
| `08_complete_pipeline.ipynb` | Complete development request: candidates, selection, execution, fallback, shared accounting, five-policy comparison. |
| `09_final_results.ipynb` | Frozen main effects, uncertainty, resources, ablations, transfer, startup/volume, variability, human agreement, errors. |

Research algorithms and plotting functions live in the package. Notebooks neither
reimplement them nor depend on another kernel's state. Default inspection loads
persisted records; generation/fitting requires an explicit execution flag and
bounded development scope. Missing artifacts explain which stage produces them.
Synthetic fixtures are labeled and used for checks, never as experimental results.

## Verification by boundary

| Boundary | Meaningful checks |
| --- | --- |
| Data/evaluator isolation | Reference fields cannot serialize into prompts, online inputs, or features. |
| Graph execution | Cycles, node limits, bindings, fan-in, deterministic order, invalid outputs. |
| Runtime and tools | Model identity, calculator restrictions, supplied-source search, cumulative limits, missing telemetry. |
| Scientific partitions | Source components never cross incompatible roles; transfer target is absent from development lineage. |
| Library and candidates | Generalization contamination, independent validation, immutable IDs, common candidates across reuse policies. |
| Fitting and prediction | Fitting-only reductions/scaling, rank/padding, grouped tuning, loaded prediction parity, no online fitting. |
| Storage and release | Atomic receipts, checksums, unknown attempts, resume, incompatible/tampered release rejection. |
| Evaluation/reporting | Scorer parity, paired population reconciliation, failure denominators, uncertainty, shared plot/query results. |

Use deterministic mock-provider end-to-end checks without external services, plus
a small real development smoke run on the execution PC. Expand checks with the
implemented boundary; do not claim empty placeholder tests provide coverage.
Run the supported quality commands in [operations](operations.md) for each code
work package. A documentation-only change needs link/path and consistency review.

## Change and completion rules

Implement one responsibility at a time, update its tests and notebook narrative,
then update the documented status. Introduce only dependencies required by that
work package. Existing helpers may be adapted after review for the new contracts;
old experiment objectives and notebook algorithms do not become another active path.

A package passes when its acceptance evidence is persisted, checked, and reviewable.
A final study passes the execution gate when all planned requests are accounted for
and immutable assets are verified. The prototype is complete when all principal
methods, datasets, planned predictor comparisons and registered supplementary
families can be reproduced, inspected, and interpreted without hidden state.