# Evaluation protocol

This is the planned protocol. Final numerical settings remain draft until the
specified development gates are passed. No benchmark performance is claimed.

## Main comparison and correctness gate

Run all five principal methods on the same eligible final questions. Report each
dataset separately. The principal reference is fresh per-question planning;
single-agent, fixed-workflow, and similarity-reuse comparisons establish context
and isolate the learned selector's contribution.

For dataset d, define delta_correctness = correctness(reuse) -
correctness(fresh planning). Declare a correctness-loss margin epsilon_d before
final execution. A correctness-preservation claim requires the prespecified lower
confidence bound to exceed -epsilon_d. A resource-reduction claim also requires a
positive, statistically supported reduction under the registered comparison rule.
Freeze the interval/test convention, confidence level, and multiplicity treatment;
do not select them after seeing results. Report absolute correctness differences
in percentage points and relative resource reductions with their denominators.

Failing the gate does not invalidate the experiment. It limits the conclusion to
the observed correctness/resource trade-off. Avoid pooling datasets to hide a loss
on one of them.

## Scoring and measurement

| Measure | Planned definition |
| --- | --- |
| HotpotQA correctness | Pinned answer exact match; answer F1 as supplementary quality. |
| DROP correctness | Pinned answer exact match with answer-type/multi-span handling; answer F1 supplementary. |
| FinQA correctness | Numerical answer accuracy under frozen normalization, units/percentage policy, and tolerance. |
| Calls | All generative calls for planning, role execution, repair, and fallback. Tool calls reported separately. |
| Tokens | Sum input and output tokens across all attempts; report both components and total. |
| Latency | Live end-to-end request wall time including encoding, candidate selection, planning, tools, repairs, fallback, and orchestration. |
| Reuse/fallback | Eligibility, qualification, reuse coverage, reasons for fallback, failed/incorrect reuse, recovery outcome. |
| Predictor quality | MCC, Brier score, calibration curves, class/support counts; supplementary discrimination and confusion summaries. |
| Resource distribution | Means, medians, tails, paired differences, budget failures, and measurement availability. |

The answer parser, binary-success criterion, tolerance, and evaluator versions are
frozen before candidate labeling. Scorers are verified on edge-case fixtures.
Supporting facts or gold programs can support named offline diagnostics; they
never control the live policy. Human judgment supplements the registered automatic
metrics and does not replace failed answers selectively.

Confirmed execution failures count as incorrect in the registered request
population. Invalid/truncated outputs follow the frozen parsing/failure rule.
Interrupted unknown effects remain explicit; report study completeness and resolve
or bound their impact before a complete-study claim. Never calculate a favorable
mean only over successful requests. Report missing telemetry as unavailable, with
coverage and sensitivity analysis where necessary.

## Required experiment families

| Family | Design | Main result |
| --- | --- | --- |
| Principal policies | Same final questions for all five policies. | Correctness gate, calls/tokens/time, reuse/fallback, paired effects. |
| Predictor comparison | Logistic regression, random forest, gradient-boosted trees, and MLP on identical held-out development candidate rows. | Predictive quality, calibration, fitting time, prediction overhead, and the validation-selected family. |
| Feature ablation | Refit 134/136/130-feature variants under matched controls. | Contribution of explicit metadata; registered live or diagnostic scope. |
| Transfer | Hold out HotpotQA, DROP, or FinQA from every development stage. | Three independent releases evaluated on their target dataset. |
| Request volume | Predeclared distinct input sequences with startup and request costs. | Cumulative cost and break-even behavior. |
| Variability | Three executions on a subset selected before inspecting final outcomes. | Correctness/selection/resource variability. |
| Human assessment | Two independent assessors, blinded registered sample. | Answer/evidence quality, error categories, agreement before reconciliation. |
| Candidate diagnostics | Extra candidate executions on a preselected final subset. | Retrieval coverage, selection errors, oracle-within-candidates diagnostics. |

Register the live scope of feature ablations and any supplementary policies using
predictor families other than the validation-selected family before the freeze.
For the primary feature ablation, keep the selected family fixed and refit and
retune each feature variant using permitted development data.
Recorded candidate replay can compare decisions where observations
exist; it cannot establish live latency, unseen fallback outcomes, or performance
of unexecuted candidates. Label replay, cached receipts, and live runs distinctly.
Oracle diagnostics are hindsight analyses, never deployable policies.

For transfer, preserve source-role separation inside the remaining two datasets.
Do not reuse the main library, reductions, calibration, thresholds, or target-derived
cost estimates. The same fixed generative-model and encoder identities may be used
across folds; any choice of their identity uses permitted development information.

## Statistical analysis

Questions within one source group are dependent. Resample source components for
paired bootstrap intervals, preserving method pairing and the registered
question-weighted estimand. Freeze resample count, seeds, confidence level, paired
test, and multiplicity families before final execution. Report effective group
counts and interval limitations if components are few or highly unequal.

Use Holm adjustment for the registered related hypothesis families. Define a
primary comparison and endpoint hierarchy so supplemental analyses do not create
unacknowledged selection. Report effects and uncertainty alongside p-values.
Cross-dataset macro summaries are supplementary to dataset-specific correctness.

Aggregate request resources with an explicit denominator and include failed
attempts. Show ratio-of-total resource reductions as well as request distributions;
do not average per-question percentages without explaining the estimand. Final
repetitions are a variability study, not extra independent source groups.

## Startup cost and workload feasibility

For a method m and N distinct requests:

`total_resource(m, N) = required_startup_resource(m) + sum(request_resource(m, i))`

Calculate tokens, calls, and time separately. Startup includes method-required
discovery failures, generalization, independent validation, candidate labeling,
encoding/indexing, tuning, calibration, training, and release preparation. Charge
the fixed-workflow method for its required development selection and fresh planning
for any method-specific preparation. Disclose shared infrastructure consistently
without double-counting it in a deployment comparison.

Separate total research expenditure (all experimental variants and diagnostics)
from deployment startup and serving expenditure. Model-fitting seconds cannot be
added to token counts. On local inference, tokens and wall time are resource
measures; do not invent monetary cost or GPU energy consumption without a declared
measurement model. Report deployment startup elapsed time and summed component
work with clear definitions if parallel activity is later introduced.

The provisional full pool implies 18,088 x 5 = 90,440 principal request executions
before node calls, library work, transfer, ablations, repetitions, or diagnostics.
Measure representative development workloads across context lengths, tables,
methods, failures, and fallback. Project each family's requests, candidate calls,
tokens, wall time, and storage. A short arithmetic smoke check is insufficient.

Acquire full eligible releases where feasible; choose full final execution or a
source-grouped sample from the measured feasibility/precision analysis. Freeze the
sample and method order before observing final outcomes. Use distinct requests for
volume curves; repeated cached answers do not represent new-request reuse benefits.
If startup never amortizes over the evaluated volume, report that result.

## Runtime controls

Record model digest, tokenizer/context/decoding controls, encoder revision,
prompt/tool hashes, dependency lock, hardware, provider version, and run scope.
Pin warm-up/loading policy, concurrency, competing-load conditions, cache treatment,
and method order. Use a seeded balanced or randomized order fixed in advance to
reduce time/order effects. Separate model-load/warm-up costs from warm request
metrics and explain their treatment in total deployment cost.

All methods share the whole-request ceilings and evidence permissions. Measure
selection and encoding overhead as part of end-to-end latency. Report cache state
and which measurements are provider-reported versus locally timed. GPU use must be
observed on the target runtime rather than inferred from hardware availability.

## Human assessment and error analysis

Select the sample by a registered procedure with dataset/method coverage. Blind
method and candidate identities; randomize presentation. Use a rubric for
correctness, evidence support, completeness, and procedural errors. Obtain two
independent ratings, calculate raw agreement and the registered kappa measure
before reconciliation, and preserve initial ratings. Resolve disagreements under
a written rule. Determine sample size and category support before final collection.

Audit selection versus retrieval failure, insufficient evidence, arithmetic or unit
errors, malformed plans, false checker acceptance/rejection, budget exhaustion,
generalization leakage, and fallback cost. Trace inspection explains measured
patterns; it is not a basis to retune the completed final release.

## Implemented answer scoring (C10)

`evaluation/scoring.py` implements evaluator-only metrics and `AnswerScore`
receipts. The current declarations in `configs/evaluation.yaml` must match the
implemented name, version, normalization and numerical tolerance; unknown or
changed declarations fail validation. The overall evaluation protocol remains
draft until its remaining population, grouping, statistical and release gates.

| Dataset | Binary success for a valid completed answer | Supplementary metric |
| --- | --- | --- |
| HotpotQA | Maximum answer EM across permitted reference alternatives equals 1. | Maximum token F1 across those alternatives. |
| DROP | Complete predicted span group has EM 1 against at least one typed answer group. | Maximum aligned span F1 across primary/validated groups. |
| FinQA | Finite numerical prediction is within absolute `0.00001` of `exe_ans`, or a categorical yes/no target matches. | Numerical difference; EM/F1 fields are unavailable for this dataset. |

HotpotQA applies the pinned evaluator's case, ASCII-punctuation, article and
whitespace normalization, multiset token F1 and yes/no/noanswer restrictions.
Only answer metrics are implemented here; supporting-fact and joint metrics
remain separate diagnostics. DROP preserves the pinned evaluator's numeric-token
normalization, hyphen tokenization, number-overlap gate, span-count-sensitive EM,
global one-to-one maximum F1 alignment and NumPy-compatible two-decimal rounding.
The alignment implementation uses the standard library and needs no SciPy/NumPy
runtime dependency. Individual spans of a multi-span answer are jointly required;
F1 below exact correctness never becomes a positive label. Empty strings are
invalid submitted answers even where a low-level metric could normalize an
article-only string to empty text.

The FinQA policy is a versioned thesis answer-level metric. It uses the C09
execution target, retaining the reported human answer separately. It does not
accept the two fields as interchangeable alternatives. Decimal comparison uses
inclusive absolute tolerance with zero relative tolerance. A terminal `%` divides
the prediction by 100: `26%` matches target `0.26`, while target `26` requires a
value of `26` in target units. No second, gold-dependent factor-of-100 comparison
is attempted. Comma-grouped numbers, one leading currency symbol (`$`, `€`, `£`),
accounting parentheses, Unicode minus and scientific notation are supported.
Currency markers introduce no conversion; magnitude suffixes such as `million`
are rejected. Nonfinite values, malformed grouping, prose, multiple numerical
alternatives and contradictory currency/percentage markers are invalid. Native
yes/no targets accept only case-insensitive yes/no, not numeric or true/false
substitutions. Numeric exponents are bounded to magnitude 1,000. This metric
reports numeric/yes-no answer correctness; executing or comparing reasoning
programs is a separate diagnostic operation.

### Submission parsing and execution states

`AnswerSubmission` identifies a task/dataset and its known execution state.
The scorer checks that identity against the evaluator reference. DROP requires
the C08 typed groups and FinQA requires the C09 distinct execution target; flat
display references are rejected. Runtime code should pass the final answer field
from a validated role/attempt result, with completion and failure metadata.

Parser `final-answer-v1` accepts plain final text, a JSON string, or a strict JSON
object containing only `answer`. DROP additionally accepts a complete string
array, directly or as JSON. Multi-span strings are not split on commas or `and`.
Duplicate JSON keys, non-string spans, empty spans, nested answer envelopes and
extra envelope keys are invalid. Code fences and prose are never repaired or
searched for a favorable embedded answer; literal text is scored as supplied.
Limits are 65,536 characters and 128 spans, recorded in the scorer identity.
HotpotQA and FinQA accept exactly one answer span.

Confirmed failed executions receive label 0 regardless of answer-like text.
Known truncation reasons (`length`, `max_tokens`, `max_output_tokens`,
`token_limit`) receive label 0. Accepted complete reasons are absent/null, `stop`,
`eos`, `eos_token` or `end_turn`; other reasons are invalid output. These checks
precede parsing/metrics. Invalid final output also receives label 0. A completed
but incorrect valid answer is `scored` with label 0; CLI success only indicates
that evaluation produced a receipt.

Unknown effects and started/unfinished executions retain null labels and metrics.
An `unknown_effect` failure code must retain the unknown state. Such records are
unavailable for selector-label fitting and remain in completeness accounting;
their treatment in final population estimates still follows the protected-study
protocol. The scorer never converts an interrupted effect into a negative
training example or a free retry. A receipt cannot claim binary success from
partial F1 or inconsistent correctness fields.

### Source pins and verification

The upstream references are immutable Git revisions; complete byte hashes appear
in `orchestrator evaluation scorers` and the reviewed fixture metadata:

- [HotpotQA evaluator](https://github.com/hotpotqa/hotpot/blob/3635853403a8735609ee997664e1528f4480762a/hotpot_evaluate_v1.py): revision `3635853403a8735609ee997664e1528f4480762a`.
- [DROP evaluator](https://github.com/allenai/allennlp-models/blob/b1f372248c17ad12684d344955fbcd98e957e77e/allennlp_models/rc/tools/drop.py): revision `b1f372248c17ad12684d344955fbcd98e957e77e`.
- [FinQA execution reference](https://github.com/czyssrs/FinQA/blob/9e2006a6ed65279a01d62e92e61c02638c7c358d/code/evaluate/evaluate.py): revision `9e2006a6ed65279a01d62e92e61c02638c7c358d`; it informs target/percentage semantics, while the thesis answer-level tolerance policy is declared above.

Development verification compared 220 HotpotQA and 2,400 DROP generated cases
against the pinned upstream functions, including span alignment and numerical
rounding boundaries. Ordinary offline CI checks a retained set of 220 HotpotQA
and 378 DROP oracle vectors in `tests/fixtures/scoring_reference_cases.json`, plus
explicit parser, numerical-tolerance, reference-type, execution-state and CLI
fixtures. These are scorer-validation inputs, not measured model predictions or
benchmark performance. No upstream network access or model calls occur in CI.

Every receipt records the scorer declaration, parser/label versions, output limits,
upstream revision/hash and normalized implementation-source hash. Its fingerprint
binds that complete identity. Source text is hashed with normalized line endings
for consistent identities across Windows/Linux checkouts. Candidate collections
and future dataset releases must bind this identity before fitting or scoring.

## Freeze and reporting

Before final execution, record the code/lockfile, source snapshots and partitions,
model/encoder bindings, prompts/tools, main/transfer libraries, feature transforms,
predictors/calibration, thresholds/cost estimates, scorers, margins, samples,
comparisons, statistics, seeds/repetitions, human protocol, hardware/cache/order,
and failure/retry rules. Reject incomplete releases. Later deviations retain their
time, reason, affected results, and new release identity.

The report must expose population/completeness, dataset correctness and uncertainty,
resource distributions, paired effects, reuse/fallback, predictor/ablation/transfer
results, startup-volume curves, variability, human agreement, and representative
traces. Every metric has dataset/method/family/fold, sample size, units, availability,
and uncertainty identifiers. Notebooks and HTML share the same stored records and
query/plot functions; metrics CSV is regenerated from those records.
