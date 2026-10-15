# Decisions and open settings

Baseline date: 15 October 2026. These are planning decisions, not completed
implementation or measured experimental settings.

## Baseline choices

| ID | Decision | Reason / consequence |
| --- | --- | --- |
| D01 | Study workflow reuse for supplied-document reasoning. | One coherent scope for correctness and resource comparisons. |
| D02 | Use HotpotQA distractor, DROP, and FinQA. | Cover multi-source, passage-based discrete, and financial table reasoning. |
| D03 | Share one generative model across methods and roles. | Isolate collaboration/selection effects from model capability differences. |
| D04 | Use a separate immutable text encoder. | Reproducible task/workflow retrieval and pre-execution representations. |
| D05 | Use coordinator/retrieval/reasoning/checking roles and DAGs of at most 12 nodes. | Bounded, inspectable collaboration. |
| D06 | Compare five principal policies. | Separate agent, fixed procedure, fresh planning, similarity, and learned reuse effects. |
| D07 | Compare LR, GBT, and a two-hidden-layer MLP; keep the configured MLP as the principal learned treatment. | Test whether nonlinear predictor complexity provides value. Model widths and superiority are not assumed. |
| D08 | Keep a versioned 140-feature main interface. | Match task/workflow representations, metadata, and compatibility under one schema. |
| D09 | Share candidates, tools, evidence, and cumulative request limits. | Avoid unequal execution permissions and hidden fallback costs. |
| D10 | Separate source-grouped development roles and freeze final releases. | Prevent source leakage and final-outcome tuning. |
| D11 | Use one package implementation for CLI and nine notebooks. | Avoid duplicate research algorithms. |
| D12 | Store detailed records/artifacts in SQLite with CSV/HTML summaries. | Keep outputs compact and queries reproducible. |
| D13 | Measure method-required startup and serving cost separately and cumulatively. | Evaluate whether reuse actually amortizes. |

Changing a baseline choice requires a dated entry stating the reason, evidence,
impacted documents/configuration, affected artifacts, and whether earlier results
remain comparable. No supervisor agreement or experimental result is implied by
this local planning baseline. The MLP treatment can be revised before the final
freeze with an explicit methodological reason and consistent study changes.

## Open decisions and blocking gates

| ID | Open setting | Resolution evidence | Must be fixed before | Owner |
| --- | --- | --- | --- | --- |
| O01 | Dataset release/source identities, licenses, actual counts, checksums. | Acquisition manifest and count reconciliation. | Snapshot publication. | `datasets.yaml` |
| O02 | Source equivalence, connected groups, role sizes, overlap treatment. | Component-size and leakage audit; feasible role support. | Discovery/collection. | `datasets.yaml` |
| O03 | Answer parsing, EM/F1 behavior, FinQA units/tolerance, binary success. | Pinned scorer fixtures and reviewed edge cases. | Candidate labeling. | `evaluation.yaml` |
| O04 | Model identity, context/output controls, evidence serialization. | Representative development pilot and target-machine metadata verification. | Measured baseline/discovery work. | `study.yaml` |
| O05 | Encoder revision, task/workflow serialization, chunking/pooling. | Retrieval feasibility and deterministic representation checks. | Library retrieval/label collection. | `study.yaml`, referenced by feature schema |
| O06 | Call/token/time/tool/repair limits and recoverable checker/failure rules. | Baseline/planning pilot including long contexts and failures. | Candidate collection and integrated comparisons. | `study.yaml` |
| O07 | Library size, admission support/success/diversity, candidate eligibility. | Independent validation coverage and measured construction cost. | Library freeze/selector collection. | `study.yaml` |
| O08 | Exact feature counting, reduction rank/padding, scaling, missingness. | Training-only rank audit and train/serve feature parity. | Predictor fitting. | `learning.yaml` |
| O09 | Search bounds, class handling, grouped stopping, calibration method/roles. | Audited label support and permitted validation performance. | Final selector fitting. | `learning.yaml` |
| O10 | Similarity/probability thresholds, tie rules, token-cost estimation. | Development coverage/correctness/resource trade-offs and cost-estimate error. | Integrated release freeze. | `learning.yaml` |
| O11 | Dataset-specific correctness margins and statistical design. | Substantive acceptable-loss rationale and development precision analysis. | Final protocol freeze. | `evaluation.yaml` |
| O12 | Full final population or grouped sample; ablation/optional LR/GBT live scope. | Workload, storage, and precision projections by experiment family. | Final protocol freeze. | `evaluation.yaml` |
| O13 | Repetition subset, human rubric/sample, candidate diagnostic subset. | Fixed sampling plan, assessors, adequate category/source support. | Final outcomes are observed. | `evaluation.yaml` |
| O14 | Cache/warm-up/order/concurrency and hardware measurement policy. | Real-PC runtime pilot and reproducible scheduling plan. | Protected execution. | `evaluation.yaml` |

Configuration filenames above are relative to `configs/`. Several target fields
will require schema extensions in their implementation package. This table does
not claim the current loader validates these scientific values. Stage progress,
freeze readiness, and `null` resolution must eventually be checked independently
of the existing scaffold check.

## Risks and planned responses

| Risk | Response and interpretation limit |
| --- | --- |
| Huge connected source components | Audit early; revise and register eligible population/grouping before collection. Do not split components invisibly. |
| Full study exceeds runtime/storage budget | Measure representative development work; register a source-grouped final sample or narrower supplementary scope before final outcomes. |
| Workflow generalization copies discovery answers | Audit templates and changed-evidence behavior; exclude contaminated procedures before admission. |
| Small library or sparse/one-class labels | Report support/effective rank; use fitting-only padding; block unsupported fitting and revise development collection explicitly. |
| Reuse saves planning but causes more incorrect answers | Apply correctness-loss gate and report failures, not only successful reuse. |
| Failed reuse plus fallback is expensive | Keep shared limits and full attempt accounting; report low-confidence versus detected-failure fallback separately. |
| Encoder/selection overhead erases savings | Include overhead in live end-to-end measurements and startup accounting. |
| Calibration or thresholds overfit | Separate grouped development roles, bound search, freeze before final execution. |
| Provider interruption produces uncertain usage | Preserve unknown attempts/availability; declare retry and sensitivity treatment. |
| Local hardware/cache/order biases timing | Record runtime state and pin the measurement/scheduling policy. |
| Transfer accidentally uses target information | Build independent fold releases and audit all fitted/admission/tuning lineage. |

## Final release checklist

A protected run requires immutable identities for code/lockfile, dataset snapshot
and roles, generative model/encoder, serialization and tools, prompts, libraries,
features/transforms, predictors/calibration, thresholds/cost estimates, scoring,
request/failure/retry rules, final sample, comparison/statistical design, repetitions,
human protocol, cache/order/hardware, and seeds. Main and transfer releases each
carry the applicable lineage.

Do not remove unresolved settings merely to make a check pass. Final execution is
blocked until required values and evidence exist. If a setting changes afterward,
retain the prior release, create a new one, and document timing and impact.

## Change record

| Date | Change | Impact |
| --- | --- | --- |
| 15 Oct 2026 | Consolidated the current workflow-reuse baseline into focused research, architecture, data, methods, evaluation, and work-package documents. | Documentation only. Runtime code, configurations, prompts, and study results remain unchanged. |
