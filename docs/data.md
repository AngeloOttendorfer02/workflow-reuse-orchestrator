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

## Implemented raw acquisition boundary

C06 adds `orchestrator data sources` and `orchestrator data acquire`, using a typed
acquisition catalog in `configs/datasets.yaml`. Normalization, scorers, source-role
assignment and canonical snapshot publication remain later work packages. The
scientific release/snapshot fields remain unresolved until verified artifacts are
bound; raw acquisition alone does not certify data readiness.

The catalog retains official HotpotQA training v1.1 and distractor-dev v1 identities,
the original DROP train/dev archive, and FinQA train/dev/public-test JSON at commit
`9e2006a6ed65279a01d62e92e61c02638c7c358d`. Source references are the
[HotpotQA homepage](https://hotpotqa.github.io/),
[AllenAI DROP page source](https://github.com/allenai/allennlp-website/blob/master/drop.html),
and [FinQA repository](https://github.com/czyssrs/FinQA).

HotpotQA and DROP hashes and byte lengths are pinned from upstream dataset metadata
linked in the catalog. The HotpotQA canonical server was unavailable during the
C06 check, so explicit immutable mirrors are configured. Their bytes must match
the original published hashes; a differently serialized mirror is rejected. The
training mirror calls its file `hotpot_train_v1.json`, but its pinned byte hash
identifies the original training v1.1 bytes. Both origin and transport are recorded.

FinQA uses a fixed Git revision and records observed SHA-256 values on first
acquisition. These are acquisition pins, not claimed upstream-published SHA-256
values. Subsequent reuse verifies original bytes against retained receipts.
Preserve manifests with raw sources when moving work to another machine.

Streaming inspection counts original JSON records and DROP questions without
loading an entire dataset into memory, extracting arbitrary archive paths, or
creating model-facing records. Raw counts include records later normalization
may exclude. Publication requires valid raw structure and configured hash/size
checks. This keeps acquisition, normalization losses, and experiment sample sizes
separate and auditable.

License metadata records the linked upstream declaration. FinQA's entry identifies
the repository MIT license; it does not relabel underlying financial reports.
Raw files and manifests remain outside Git under `data/raw`. See
[operations](operations.md#acquire-raw-benchmark-sources) for the commands.

## HotpotQA normalization (C07)

`data normalize --dataset hotpotqa` reads only acquired, checksummed native
train/dev files. It streams records into one unpartitioned SQLite staging artifact
under `data/processed`; it does not publish a frozen `datasets.sqlite3` snapshot.
Separate tables hold model-facing inputs, evaluator references, source versions,
ordered task/source links, native provenance, and exclusions. The input loader
selects only the input table; evaluation references require an explicit separate
loader. Both loaders verify their record checksums and use read-only connections.

Task IDs are `hotpotqa:<native_id>`. Article identities hash NFC-normalized titles
with underscores treated as spaces and whitespace collapsed; original title text
is retained. Paragraph identities hash the exact title and ordered sentence list.
Sentence-content hashes also support the later duplicate-source audit. These
identities expose article variants without claiming that all aliases or
near-duplicates have already been resolved; that audit belongs to C11.

Every supplied paragraph remains in its native order, including distractors.
Sentence text, formatting and blank sentence slots are preserved exactly, so
zero-based evidence locations remain meaningful. A passage must still have some
non-blank text. Gold supporting facts, their resolved evidence locations, answer,
question type and difficulty remain evaluator-only. Invalid support locations are
retained as warnings without selecting context or excluding an otherwise valid
question. No alternative answers are invented for the native single-answer field.

The per-split audit reconciles `raw = retained + duplicates + malformed`.
Identical repeated task IDs within a native split retain the first occurrence and
record later occurrences as exclusions. Conflicting records with the same native
ID stop publication. The same ID in different native splits remains in both split
tables for the C11 source-group audit. Different IDs with equal content also stay
available for that audit. Invalid IDs, questions, answers or paragraph structure
receive stable exclusion reasons with raw indexes and record hashes. Invalid JSON
or a changed acquisition receipt fails the operation rather than publishing a
partially processed artifact.

Normalization binds the adapter version, release/source-plan identity, selected
source hashes, counts and a deterministic logical content hash. An identical rerun
verifies the existing artifact without rewriting it. Different content requires a
new output path; corrupt existing output fails explicitly. Publication is atomic
and a single-writer lock protects the output. Raw source hashes are checked before
and after reading.

Structural validation of the pinned dev file retained all 7,405 questions, with no
duplicate-ID or malformed-record exclusions. It preserved blank sentence slots in
49 questions and flagged one question with an out-of-range supporting-fact index.
These are preparation audits, not experimental correctness results. Scientific
roles, cross-source leakage checks and final snapshot publication remain C11/C12.
