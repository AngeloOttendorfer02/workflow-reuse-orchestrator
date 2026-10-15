# Research plan

## Problem and objective

A multi-agent system can spend substantial inference effort deciding how agents
should collaborate. Repeating that planning for similar questions may be wasteful.
Conversely, reusing an unsuitable collaboration can produce incorrect answers or
incur both a failed attempt and a new plan.

The project will evaluate reusable procedures for questions over supplied text and
tables. A workflow specifies roles, dependencies, evidence use, and answer
production. Reuse means executing that procedure on the new question's evidence;
it does not mean returning a stored answer.

The objective is to determine when workflow reuse preserves correctness and reduces
request-time and total resource use. The contribution is a reproducible selection
and evaluation system, with traceable evidence about benefits and limitations.

## Research questions

| ID | Question | Evidence |
| --- | --- | --- |
| RQ1 | How much do similarity and success-prediction reuse change correctness, tokens, calls, and latency relative to fresh planning on each dataset? | Paired five-policy evaluation with correctness-loss gates and uncertainty. |
| RQ2 | Does a learned success predictor improve candidate selection over similarity, and how do logistic regression, gradient-boosted trees, and an MLP compare? | Identical held-out candidate examples, MCC, Brier score, calibration, and selection diagnostics. |
| RQ3 | How much do explicit task and workflow metadata contribute beyond text representations? | Refitted 134-, 136-, and 130-feature MLP ablations against the 140-feature model. |
| RQ4 | Can a library and selector developed without one dataset transfer to that dataset? | Three independently developed leave-one-dataset-out releases. |
| RQ5 | At what request volume, if any, does reuse repay its startup cost? | Measured discovery, validation, labeling, fitting, and request costs across distinct request sequences. |

The principal quantitative question is RQ1: relative reductions in total request
tokens and end-to-end latency are assessed subject to a dataset-specific bound on
correctness loss. Margins and statistical precision are fixed after development
pilots and before final evaluation; no numerical benefit is assumed in advance.

## Hypotheses

The working hypotheses are that suitable reuse can reduce planning overhead; that
success prediction can distinguish candidates that are semantically similar but
procedurally unsuitable; and that explicit structural metadata can improve this
prediction. Startup work may require substantial volume to amortize, and transfer
may reduce coverage or correctness. These are testable expectations. Null results,
negative effects, and dataset-dependent trade-offs remain valid outcomes.

## Scope

| Included | Boundary |
| --- | --- |
| Supplied-document question answering | HotpotQA distractor, DROP, FinQA; evidence is provided with the question. |
| Four agent roles | Coordinator, retrieval, reasoning, checking. |
| One generative model | Shared by every agent, planner, generalizer, baseline, and transfer fold. |
| Frozen encoder | Separate from the generative model; used for task/workflow representations. |
| Reusable collaboration graphs | Bounded DAGs with at most 12 nodes and typed bindings. |
| Five principal policies | Single agent, fixed workflow, fresh planning, similarity reuse, learned reuse. |
| Three predictors | Logistic regression, gradient-boosted trees, two-hidden-layer MLP. |
| Inspectable prototype | CLI, nine notebooks, database, report, and selected execution traces. |

Multi-model routing, external browsing, arbitrary executable agent code, unbounded
agent debates, production hosting, autonomous changes to the final library, and
open-ended business task generation are outside the core study. Extra methods must
answer a registered question and fit the measured workload budget.

## Research integrity

Final reference answers, supporting facts, and gold programs never enter agent
prompts or selection features. A checker assesses observable consistency; it is not
a correctness oracle. Offline scoring determines correctness after execution.

Development roles separate workflow discovery, independent library validation,
selector fitting, validation, and calibration. Final evaluation loads a frozen
release and performs no fitting, threshold tuning, or library admission. Transfer
folds also exclude the held-out dataset from every development-dependent choice.

## Deliverables and completion

| Deliverable | Required result |
| --- | --- |
| Dataset snapshots | Reproducible normalization, source groups, references, and partition manifests. |
| Workflow runtime | Typed graphs, evidence tools, shared limits, and complete attempt traces. |
| Libraries and selectors | Independently validated procedures and reproducible fitted state. |
| Frozen study | Main comparison and the registered supplementary families. |
| Compact reporting | Dataset-specific effects, uncertainty, failures, cost accounting, and inspectable examples. |
| Notebook suite | Nine independent narratives using package functions and measured records. |
| Reproduction bundle | Identifiable code, environment, settings, data, models, and artifacts. |

Engineering completion means these deliverables work and reconcile. Scientific
success means the resulting evidence answers the questions credibly, whether or
not learned reuse outperforms its baselines.
