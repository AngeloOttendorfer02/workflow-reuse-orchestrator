# Data plan

## Datasets and task construction

| Dataset | Purpose | Input available to the system | Evaluator-only fields | Planned final source pool |
| --- | --- | --- | --- | --- |
| HotpotQA distractor | Multi-document reasoning amid distractors. | Question and supplied context paragraphs/sentences. | Reference answer and supporting facts. | Public development split. |
| DROP | Discrete reasoning over passages. | Question and passage with preserved structure. | Reference answer forms, types, and annotations. | Public development split. |
| FinQA | Numerical reasoning over financial text and tables. | Question, supplied report text, table rows/cells. | Numerical answer and gold program/annotations. | Public test split. |

Use public training releases for development roles, subject to source-group
separation from the final pool. FinQA public development data may support a named
development role if its source groups are eligible; it is not automatically a
calibration set. Dataset-native split names do not replace scientific role checks.

The prior design's planning counts are 7,405 HotpotQA, 9,536 DROP, and 1,147 FinQA
questions: 18,088 in total. These are provisional source-pool counts, not acquired
or retained observations. Record actual counts from pinned releases. No arbitrary
3,000-task cap is imposed. Full acquisition and the eventual executed final sample
are separate decisions based on feasible grouping and measured workload.

## Acquisition and provenance

For each source retain release identity, canonical source location, acquisition
time, original split, license/usage conditions, byte checksum, and adapter version.
Do not silently replace a source after collection. Preparation must reconcile raw,
normalized, excluded, duplicate, and retained counts with reasons.

Raw bytes remain immutable. Canonical records use stable dataset-prefixed task IDs
and source IDs. Snapshot identity binds source hashes, preparation/scoring versions,
and the partition assignment. Re-running preparation with the same inputs must
produce equivalent canonical content and assignments.

## Canonical representation

| Record | Required fields or behavior |
| --- | --- |
| Task | Stable ID, dataset/release, raw split, question, source references, content hash. |
| Source | Stable article/passage/report identity, text, provenance, content hash. |
| Evidence locations | Paragraph/sentence offsets or table/row/column/cell coordinates. |
| Table | Headers, row order, cell strings, units, original serialization context. |
| Reference | Answer alternatives, answer type, evaluator support/program information. |
| Source relation | Task-to-source links and equivalence/duplicate links used for grouping. |
| Partition | Connected group, scientific role, fold, assignment version/seed. |
| Exclusion | Stable input identity, reason, affected stage, count. |

The supplied context must preserve enough structure to locate evidence and perform
calculations. Keep number formatting and units; numerical parsing is a separate,
versioned operation. Do not flatten away table headers or silently discard rows.

Prepared inputs and references live in separate logical tables in
`datasets.sqlite3`. The online-facing loader returns only `TaskInput`. A separate
evaluator loader exposes references after execution or for permitted development
labeling. Gold support annotations must not select passages for agents.

## Scientific roles and leakage prevention

Assign connected source groups, not independent question rows:

| Role | Permitted use |
| --- | --- |
| Discovery | Generate successful procedures and candidate generalized templates. |
| Library validation | Independently assess generalized templates for admission. |
| Selector fitting | Collect candidate labels and fit transformations/predictors. |
| Selector validation | Compare predictors, tune hyperparameters and selection controls. |
| Selector calibration | Fit declared probability calibration without refitting the base predictor. |
| Final evaluation | Execute the frozen study; no development decisions. |

Threshold selection uses a declared validation role or a dedicated additional
source-grouped role. Do not tune on calibration data without explicitly registering
that use and its limitations. Decide population sizes only after the group audit.

Build an undirected relation between questions sharing a source or a declared
near-duplicate source; connected components are assignment units. Audit article
aliases, duplicate passages, shared financial reports, and cross-dataset overlap.
No source component may cross incompatible scientific roles.

HotpotQA distractor sources may connect many questions into a large component.
Measure this before choosing fractions. If the rule makes a split infeasible,
record the issue, revise the grouping/task-population protocol using development
information, and freeze it before expensive collection. Do not break components
silently. Final-pool overlap must be excluded from development and counted.

In leave-one-dataset-out transfer, remove the target dataset from discovery,
library validation, candidate collection, representation fitting, predictor tuning,
calibration, threshold selection, and cost estimation. Use a separate release per
fold; relabeling the main release as a transfer release is invalid.

## Length, representations, and missing data

Measure context length and its tails before setting model limits. Pin evidence
serialization, any chunking/selection, truncation rules, encoder pooling, and
answer-output limits. All methods receive equivalent evidence opportunities.
Context selection cannot depend on gold answers or supporting facts. Record any
omitted evidence and distinguish context exclusion from model failure.

A long or malformed input cannot disappear after its outcome is seen. Before the
freeze, define eligibility and exclusion rules and report counts per dataset.
Execution failures remain in the correctness population under the evaluation
protocol. Unknown interrupted observations are separately identified.

Encoder caches bind content hashes, immutable encoder/tokenizer revision,
serialization, chunking, pooling, and normalization. Cache misses are recomputable;
a changed binding creates new cache identities.

## Scoring readiness and preparation outputs

Verify dataset-specific normalization on fixtures before generating success labels.
HotpotQA and DROP require answer EM/F1 with the pinned reference behavior; FinQA
requires a declared numerical-answer normalization and tolerance. Gold programs
can support evaluator diagnostics, not model prompts. Binary training success is
specified in [methods](methods.md) and [evaluation](evaluation.md).

Preparation is accepted when:

- All retained questions round-trip their text, tables, and evidence locations.
- Input serialization and features contain no evaluator-only fields.
- Source counts, component sizes, overlaps, assignments, and exclusions reconcile.
- Scorer fixtures cover aliases, numeric forms, units, spans, and malformed outputs.
- A manifest binds releases, checksums, adapters, scorers, assignments, and counts.
- Notebooks 01/02 inspect development data and reproduce the audit from artifacts.

Data files and generated snapshots remain outside Git. Commit preparation code,
small deterministic fixtures, schemas/configuration, and the documentation.
