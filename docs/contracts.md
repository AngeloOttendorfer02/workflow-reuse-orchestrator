# Workflow and request contracts

C04 implements validation and local accounting; C05 adds durable job transitions,
identity/lineage and incremental results as described in [persistence](persistence.md).
Role runners, graph execution and planning/recovery policies are later work. Validating
a contract does not execute a workflow or establish answer correctness.

## Workflow versions and bindings

| Contract | Meaning |
| --- | --- |
| `Workflow` / `WorkflowNode`, `workflow-v1` | Existing graph-only declaration with roles, instructions and dependencies. Still readable; not implicitly promoted to a bound workflow. |
| `BoundWorkflow` / `BoundWorkflowNode`, `workflow-v2` | Complete binding declaration with named typed input slots and fixed role output ports. Future execution uses this contract. |

Both versions require 1-12 uniquely named nodes, existing non-self dependencies,
no duplicate edges/cycles, an existing final node and every node contributing to
that final node. Ready nodes are ordered by identifier; independent nodes remain
sequential in the planned executor.

Each v2 input contains `name`, `kind` and `value`. `value.source` selects one of:

| Source | Allowed fields | Validation |
| --- | --- | --- |
| `task` | `field: question` or `field: documents` | `kind` equals the field. Documents mean the current passages/tables, never reference answers. |
| `node` | `node_id`, `output` | The node is a declared direct predecessor; its role exposes the port; `kind` equals that port's type. |

Input names are unique per node, with 1-32 slots. Multiple predecessor outputs can
have the same type under different names, allowing explicit fan-in. Every declared
dependency must provide at least one input. Arbitrary property paths, evaluator
sources, unknown fields and nonexistent ports are rejected.

Every node requires the current question. Retrieval also requires documents.
Reasoning/checking requires documents or evidence; checking additionally requires
a predecessor answer. The final node is reasoning and exposes `answer`.

Outputs are canonical rather than caller-renamable:

| Role | Output ports and values |
| --- | --- |
| `coordinator` | `plan`: 1-12 nonempty procedural steps. This is in-graph guidance; graph planning/generalization is later work. |
| `retrieval` | `evidence`: up to 64 sentence/cell references. |
| `reasoning` | `answer`: nonempty text; `evidence`: up to 64 references. |
| `checking` | `check`: verdict `pass`, `fail` or `uncertain` plus nonempty rationale; `evidence`: up to 64 references. |

`examples/bound_workflow.json` illustrates retrieval, reasoning, checking and a
final answer node. It has no task-specific answers or evidence locations. To
validate it in Python from the repository root:

```python
from pathlib import Path
from workflow_reuse_orchestrator.domain.workflows import BoundWorkflow

workflow = BoundWorkflow.model_validate_json(
    Path("examples/bound_workflow.json").read_text(encoding="utf-8")
)
assert workflow.topological_order() == ("retrieve", "reason", "check", "final")
```

There is no workflow execution CLI yet. The v2 validator reuses the v1 structural
validator internally but does not convert stored v1 records or infer bindings.

## Current-task evidence and reference isolation

`TaskInput` contains question, supplied passages/tables and identity. Unknown
fields are forbidden, including answer/annotation/free-form metadata fields.
`EvaluationReference` remains a separately loaded evaluator-only object. Task
bindings expose question/documents, excluding dataset identity and references.

Sentence evidence contains task/source/passage identity and a zero-based sentence
index. Cell evidence contains task/source/table identity plus zero-based row and
column indices. `resolve_evidence` verifies all identities and bounds against the
current task and returns the exact supplied text. Ragged tables retain their real
row lengths. A location from another task or nonexistent source cannot resolve.

`validate_role_output_json(payload, node=..., task=...)` strictly parses the tagged
role output, checks its declared role, rejects duplicate references and resolves
every cited location. Empty evidence is permitted and observable. A structurally
valid answer or a check verdict is not an evaluator score. No gold signal enters
this validation. Preventing answers from being embedded in free-text reusable
instructions additionally requires the later library generalization/admission work.

`TaskInput.observable_metadata()` computes question character count, passage count,
sentence count, table count and cell count. These are descriptive input counts,
without dataset ID, golds, costs or checker outcomes. They do not define the four
task metadata features: C25 will fix the exact units/order of the 140-feature
interface. No feature extractor or predictor is implemented here.

## Attempts and failures

`AttemptOutcome` (`attempt-v1`) identifies request, attempt and kind (`primary`,
`reuse`, `fallback`). `cumulative_usage` is a snapshot of the original request
tracker, including earlier attempts, planning, repair and tools. Do not add these
snapshots together as separate bills.

| State | Answer | Failure code |
| --- | --- | --- |
| `started` | Absent | Absent |
| `succeeded` | Required | Absent |
| `failed` | Absent | Required; cannot be `unknown_effect`. |
| `unknown` | Absent | Exactly `unknown_effect`. |

Failure codes cover invalid workflow/output, provider/tool errors, exhausted
budget, cancellation and unknown effect. Unknown means the external effect cannot
be safely declared completed or free. Snapshot validation does not enforce a
history of attempt transitions. C05 persists attempt identities and job state/events;
later policies own the complete request/attempt lifecycle and fallback decisions.
Historical generic `Receipt` records keep their existing shape.

## One cumulative allowance

Create one `BudgetTracker` per request and share it among all generation and tool
entry points, including repair/fallback work. It has no reset API; its budget is
read-only. `AttemptOutcome` does not allocate a new tracker.

| Situation | Accounting behavior |
| --- | --- |
| Generation admitted | Reserve positive input/output bounds and count the call before provider contact. Pending tokens are unavailable. |
| Measured completion | Reconcile actual input/output tokens independently. The wrapper conservatively reserves the configured context as the input upper bound. |
| Missing measurement | Preserve `None` for that token total; retain any independently known total. Further generation is blocked because a safe token reservation is impossible. |
| Provider failure/cancellation | Count the attempted call, clear the pending reservation and mark both token totals unavailable. Propagate the original exception/cancellation. |
| Usage exceeds reservation | Record the observed excess and block subsequent effects. Never truncate the recorded usage to its allowance. |
| Tool attempt | Check allowance, count before invocation, keep the count on failure/cancellation. Both local tools share this counter. |
| Repair/fallback | Consume explicit allowances before their work; all subsequent effects use the same call/token/tool/deadline limits. At most one fallback is allowed. |
| In-flight model/tool | Block overlapping/nested model calls, tools and repair/fallback admission. This tracker supports sequential execution. |
| Deadline | Generation receives remaining whole-request time. Successful late effects retain measured cost and raise `BudgetExceeded`; failed late tools preserve their original exception and block subsequent work. |

`ResourceUsage.wall_seconds` is monotonic elapsed request time, not the sum of
provider component timings. Tools may remain usable after unknown model tokens if
their own allowance/time permits, but generation cannot resume. Synchronous tools
are checked before and after invocation; there is no forced interruption at the
exact deadline. Provider/network cancellation also cannot prove that remote work
never happened. Future persistence must preserve that uncertainty.

## Local tools

`SuppliedSourceSearch` searches only the `TaskInput` bound at construction. Queries
contain 1-256 characters and 1-32 distinct word terms; limits are integers from
1-20. Case-folded whole-word matching ranks by distinct matched terms, then stable
passage/sentence/table/cell order. It returns exact text and typed evidence
locations, including an empty hit set when nothing matches. It opens no external
document, URL, file or evaluator reference. Scanning cost depends on supplied
context size; this is a local lexical evidence tool, not workflow retrieval.

`SafeCalculator` retains isolated 28-digit Decimal arithmetic, finite magnitude
bounds, 256-character expressions, whitelisted operators, bounded integer powers
and Python floor/remainder behavior. C04 also caps traversal at 128 syntax nodes.
It does not execute Python expressions through `eval`, names, calls or attributes.

`RequestTools(task=task, tracker=tracker)` exposes counted `search` and `calculate`
entry points. Future role runners must use this facade. Low-level tool APIs remain
available for direct unit testing and are not implicitly counted. Tool result
types/protocols live in `domain/providers.py`; importing `CalculatorResult` from
`runtime.tools` remains compatible. These implementation caps must be included in
the eventual frozen tool/protocol identity; they are not measured study settings.