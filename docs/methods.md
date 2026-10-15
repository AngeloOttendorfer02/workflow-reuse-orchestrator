# Methods and algorithms

This document specifies planned methods. None of the workflow, encoder, or
predictor behavior is implemented in the current scaffold.

## Common experimental controls

Every principal method uses the same generative-model fingerprint, decoding
controls, supplied evidence, applicable tools, answer schema, and whole-request
ceilings. One executor performs all model/tool effects and records their cost.
One agent may make several calls; agent count and call count are different metrics.

A workflow is a typed DAG with at most 12 nodes. Nodes bind role instructions to
current-task evidence and predecessor outputs. Graph identity includes canonical
structure and instructions. Free-form executable code is not a workflow format.

## Principal policies

| Method ID | Decision rule | Planning and recovery |
| --- | --- | --- |
| `single-agent` | One agent solves the question using a bounded evidence/calculator loop. | No collaboration planner; declared output/tool repair only. |
| `fixed-workflow` | One graph selected using development evidence is used for every eligible question. | No task-specific replanning; no hidden planner fallback. |
| `per-question-planning` | Coordinator creates a new graph from the question and supplied context. | Declared malformed-plan repair limit; planning cost is included. |
| `similarity-reuse` | Select the highest-similarity eligible candidate passing a development-frozen similarity threshold. | If none qualifies or a declared failure is detected, permit one fresh fallback plan. |
| `prediction-reuse-mlp` | Qualify candidates by calibrated success probability, then minimize estimated token use. | Same candidate pool and fallback rule as similarity reuse. |

Select the fixed graph on development data and freeze its topology and instructions.
Do not choose one after looking at final outcomes. A fixed workflow can resolve
current evidence dynamically, but its collaboration graph stays fixed.

## Fresh planning and graph validation

The coordinator receives reference-free input and the allowed roles/tools/limits.
It returns a structured graph. Reject malformed bindings, cycles, unknown roles,
inaccessible answer nodes, and graphs exceeding the node ceiling before execution.
Permit only the declared number of plan repairs, charged to the same request.
Planning failure is an observed outcome, not an excuse to drop the question.

Role prompts request usable intermediate results and evidence. Store concise
structured outputs needed for inspection; the study does not require disclosure
of private internal model reasoning.

## Library construction

1. Plan and execute discovery questions from permitted source groups.
2. Score discovery outcomes with the frozen development scorer; retain successful
   procedures as candidates and account for unsuccessful discovery attempts.
3. Generalize candidate procedures into reusable instructions and input placeholders
   using the same model. Remove question-specific names, values, answers, and
   source-specific evidence bindings while preserving necessary procedure types.
4. Canonicalize graph structure and instructions and deduplicate candidates.
5. Execute generalized templates on independent library-validation questions with
   fresh evidence. Record support, correctness, failures, and resource use.
6. Apply the development-defined support, success, diversity, and size rules.
7. Freeze admitted templates, retrieval representations, lineage, and all admission
   rules before collecting selector labels.

Admission must not rely solely on the discovery question. Audit templates for
answer contamination and test behavior under changed entities/values/evidence.
Record rejected candidates and their creation/validation expenditure. Maximum
library size, minimum support, admission success threshold, and retrieval eligibility
are pilot decisions in [decisions](decisions.md).

## Candidate retrieval

Use one frozen text encoder and pinned serialization/chunking/pooling rules. Embed
the observable task input and generalized workflow descriptions. Retrieve up to
three eligible templates using cosine similarity, with stable graph-ID tie-breaking.
Similarity reuse and learned reuse receive the same candidate IDs for a request.

Define the exact task/context representation before collecting labels. Do not use
gold answers, supporting facts, programs, dataset identity, or current-task measured
execution outcomes. Preserve the empty-library and no-eligible-candidate cases;
these lead to declared fallback rather than invented candidates.

## Candidate-success data

For each eligible development question, execute the common candidate set through
the same runtime and score each outcome. Each row identifies task, source group,
workflow/library version, attempt, scientific role/fold, label, and usage.

Binary success is 1 for an answer satisfying the frozen dataset-specific correctness
rule and 0 for a confirmed incorrect answer or terminal execution/output failure.
Partial overlap F1 is a reported metric, not automatically binary success. The
precise EM/numeric criterion and normalization must be fixed before labeling.

An interrupted observation without a known outcome remains unknown and is not
converted to 0 or 1. Keep all-zero candidate sets; discarding them would hide the
selector's hardest cases. Define collection and retry rules before running them.
Report class balance, candidate coverage, missing labels, and source-group support.

## Feature contract

The principal candidate-success interface has 140 named, ordered columns:

| Group | Width | Planned definition |
| --- | ---: | --- |
| Task representation | 64 | Frozen question/context representation reduced using fitting data only. |
| Workflow representation | 64 | Frozen generalized graph/instruction representation reduced using fitting data only. |
| Task metadata | 4 | Context length, source count, table-cell count, numerical-value count. |
| Workflow metadata | 6 | Agent steps, dependency depth, retrieval steps, reasoning steps, checking steps, handoffs. |
| Compatibility | 2 | Question-workflow similarity and question-context similarity. |
| Total | 140 | Fixed schema shared by training and online prediction. |

Before implementation, freeze units and counting rules: context length is measured
under the declared tokenizer; source count counts distinct supplied sources;
table-cell counting declares header handling; numerical-value counting declares
parser/duplicates; dependency depth declares edge versus node convention; a
handoff declares how fan-out/fan-in edges are counted. Representations must specify
which question/context text each similarity uses. These are explicit pilot decisions,
not arbitrary choices made independently in training and serving.

Fit dimensionality reduction, imputation if needed, and scaling only on selector
fitting groups. Fit the workflow reducer using admitted-library representations
within that scope. With fewer than 64 independent observations, preserve a recorded
rank limit and zero-padding rule; report effective rank. Validation or final vectors
cannot be added to make a 64-dimensional fit possible. Never pad missing measurements
as if they were observed zero values.

Current-task outcome, measured cost, checker verdict, reference answer, gold program,
and dataset ID are excluded from pre-execution features. Development-derived token
cost estimates are separate selection inputs, not observed costs of the new request.

## Predictor fitting and calibration

| Predictor | Purpose | Planned implementation |
| --- | --- | --- |
| Logistic regression | Simple linear probability baseline. | Regularized classifier with fitting-only preprocessing. |
| Gradient-boosted trees | Nonlinear tabular comparison. | Histogram-based gradient boosting. |
| MLP | Principal configured success predictor. | Exactly two hidden layers; widths selected on development data. |

Use one shared feature/label collection and source-grouped external evaluation.
Bound the search size, random seeds, iteration budgets, class-handling choices,
regularization, and stopping rules. Disable or replace automatic internal random
validation when it would mix source groups. A one-class or insufficient-support
population blocks normal fitting until a declared resolution is recorded.

Tune hyperparameters using validation groups. Fit the declared calibration on its
permitted held-out role and compare calibration with Brier score and reliability
plots. Select thresholds and cost-estimation rules using development information
only. Save preprocessing, predictor, calibration, feature order/rank, thresholds,
version identities, and fitting lineage together. Loaded and in-memory prediction
must agree. The MLP is a study treatment, not a claim that it is the best model.

## Learned selection and fallback

For the common candidate set C, let p(w | x) be calibrated predicted success,
tau the frozen threshold, and c_hat(w, x) the development-derived token estimate.
Define Q = {w in C : p(w | x) >= tau}. If Q is nonempty, select the member with
minimum c_hat and break ties by stable workflow identity. Estimate costs from
permitted development receipts under a frozen aggregation model; report estimate
error separately. Do not execute a candidate to learn its cost before selecting it.

If Q is empty, start one fresh fallback plan. If attempted reuse has a declared
schema/tool/runtime failure or checking verdict that triggers recovery, that same
fallback remains available once. `uncertain` checker handling and recoverable failure
codes must be frozen. A gold mismatch never triggers fallback. Resource exhaustion
or exhausted recovery yields a recorded terminal failure.

Fallback uses the remaining original allowance. Failed reuse and fallback costs are
both included in request totals. Report successful reuse, no-candidate/low-confidence
fallback, detected-failure fallback, undetected incorrect reuse, and exhausted budgets.

## Ablations and comparisons

Refit and retune the MLP after removing six workflow metadata columns (134 total),
four task metadata columns (136), and both groups (130). Keep library, candidate
retrieval, permitted tasks, and execution permissions matched. These ablations
remove explicit metadata; embeddings may still encode related properties.

LR/GBT/MLP predictor comparisons use identical held-out candidate examples. Full
live policy runs with LR or GBT are a supplementary scope decision to register
before final evaluation. Transfer uses separately constructed libraries and fitted
state for each excluded dataset. [Evaluation](evaluation.md) defines the complete
experiment families and the limits of offline replay claims.
