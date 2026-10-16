# Persistence, progress and resume

C05 adds durable work units to the existing SQLite receipt/artifact store. The
infrastructure pilot uses this ledger. Scientific stage callbacks, full agent
execution, candidate decisions, scoring and reporting remain later work.

## Versions and identity

| Version | Behavior |
| --- | --- |
| Result database schema 1 | Existing receipts, immutable bindings and artifacts remain readable, including historical method IDs. No job history is assumed. |
| Result database schema 2 | Adds runs, scopes, requests, attempts, jobs and ordered events. New databases use this version. |
| `job-v1` | JSON contract for one job state; independent of database schema version. |

Opening schema 1 does not upgrade it. `pipeline migrate --output DIR` explicitly
adds the new tables/indexes and changes `PRAGMA user_version` in one transaction,
after checking existing integrity. It preserves original receipt/binding/artifact
rows and does not reconstruct historical jobs, method/fold lineage or usage.
Corruption, unsupported versions and unversioned populated databases are refused.

The ledger contains:

| Table | Identity and purpose |
| --- | --- |
| `runs` | Run ID, purpose, configuration hash and code version. Immutable. |
| `scopes` | Scope ID, run ID, family and explicit fold ID. Immutable. |
| `requests` | Request ID, scope, task, method and original request budget. Immutable. |
| `attempts` | Attempt ID, request ID and primary/reuse/fallback kind. Immutable. |
| `jobs` | Unit ID, scope, stage, phase, method, optional request/attempt, retry predecessor, state, result and incremental usage. |
| `events` | Monotonically ordered declaration/start/completion/interruption snapshots for each job. Append-only through the API. |

Job phases are `startup`, `request` and `analysis`; effect kinds are `local`,
`model` and `tool`. `local` is reserved for host-owned work without external
effects. Request/attempt identities must occur together, and are mandatory for
request-phase jobs. The store verifies request scope/method and attempt ownership.
Startup jobs still require method and fold lineage; common infrastructure is
recorded as `infrastructure-pilot` / `infrastructure`, not charged to one principal
policy by implication. Later discovery/fitting code supplies its actual scope.

`ResultStore.jobs` can filter by run, request or attempt. The current pilot's code
identity includes package version and hashes of installed Python source bytes.
This is recorded provenance; protected-release verification is still a later gate.

## Durable boundaries

`JobRunner.run` declares or reads the immutable job identity, commits start intent,
then invokes its callback. A fresh completion atomically stores job state, result,
usage, completion event and any supplied mirror receipts. A receipt conflict rolls
back that completion transaction. Start intent and optional start receipts are
also atomic; if intent fails, the callback does not run.

| State | Meaning and resume behavior |
| --- | --- |
| `pending` | Declared, not admitted. May start. |
| `running` | Start intent committed, no durable terminal result. Cannot replay. |
| `succeeded` | Result committed. Resume returns the stored result without calling the operation. |
| `failed` | Known terminal failure/result. Resume returns that failure without replay; another execution needs a retry identity. |
| `unknown` | Completion/effect is uncertain. Never silently replay or report it as success. |

An external model/tool exception or cancellation becomes `unknown`. A caught
failure of a declared local unit becomes `failed`. After a hard process exit,
explicit writer recovery marks every in-flight unit unknown, including local
units; it does not guess how far execution reached. Read-only inspection reports
stored `running` state without performing this recovery. The runtime-check command
recovers its own pilot run before refusing an unfinished job or admitting a retry.

Known measurements survive failure and result-save conflicts where available.
If the process died before durable measurements existed, model intent retains
one admitted call with unavailable token counts. An intent can exist even if the
process died before provider contact: it represents possible cost, not proof that
the remote model ran. Hard-crash wall time stays unavailable. Recovery timestamps
record when uncertainty was recognized, not the unknown remote completion time.

No database transaction can guarantee exactly-once external generation. The
implementation avoids replaying known completed effects and conservatively keeps
uncertain effects and costs.

## Explicit retries and original budgets

A retry is a new job with `retry_of` pointing to a failed/unknown predecessor.
Scope, stage, phase, method, effect and parameters must match. Each predecessor
has at most one direct retry; further retries follow that chain. When attached to
a request, the retry needs a new request/attempt identity while retaining the
original task, scope, method and declared limits. The predecessor remains intact.

This new identity is an explicit **new trial**, not a continuation that resets a
policy's allowance. Within an active request, roles, planning, repair, reuse and
fallback must still share the original C04 `BudgetTracker`. The store refuses new
effects within an unknown request and overlapping in-flight jobs. C05 does not
restore a live monotonic deadline across restarts or decide a scientific retry
policy. Those rules must be registered before protected experiments.

An old schema-v1 pilot has no recoverable job/retry lineage. Migration does not
create it. Historical completed receipts can still be read; an unfinished legacy
pilot requires a separately identified new output folder/trial.

## Cost and progress semantics

`JobResult.usage` and stored `JobRecord.usage` are **incremental unit costs**. They
are distinct from C04 `AttemptOutcome.cumulative_usage`, which snapshots the whole
request. Do not add cumulative snapshots to job totals or count both the ledger
and its mirror receipts as separate model calls. Host callbacks must supply
incremental costs, not a shared tracker's lifetime total for every child job.

`ResultStore.progress` reports planned/pending/running/succeeded/failed/unknown
counts, phase counts, scopes/folds, current job identities, unknown job IDs and
available aggregate usage. It sets `usage_basis: incremental_job_costs` and exposes
receipt count separately. The usage sum covers only ledger jobs: historical or
other unlinked receipts are not silently added, interpreted as zero expense, or
claimed to be fully accounted for. A migrated database with no jobs may therefore
show zero ledger costs despite having historical receipts.

Missing input/output token totals remain `null` independently when any admitted
job lacks that measurement. Aggregate wall time is `null` if any admitted job has
unknown duration; per-job `wall_time_available` distinguishes that state from a
measured zero. Known wall durations sum sequential unit execution times, not
whole-run elapsed time, queue delay, metadata inspection or the request tracker's
full lifetime. These metrics must not be presented as final end-to-end latency.

Progress callbacks include event, phase, stage, job, method, fold and the progress
snapshot. The pilot prints phase/count updates to stderr and one final JSON
report to stdout. `pipeline status` is a snapshot, not a live dashboard. It returns
success when inspection succeeds even if stored jobs are failed/unknown.

## Writer exclusion and integrity

One cooperative writer holds an OS lock on `results.sqlite3.lock` for the store's
entire lifetime, including external calls. POSIX uses `flock`; Windows uses a
one-byte nonblocking `msvcrt` lock. The OS releases it on close/process exit. The
small lock file remains so processes continue locking the same path; never delete
it to bypass an active writer. SQLite foreign keys and short write transactions
provide database consistency while read-only observers inspect committed state.

The lock governs writers using `ResultStore` on the same local filesystem path;
it does not police unrelated raw SQL clients or promise distributed/network-drive
coordination. This remains a local application.

`verify_integrity` checks SQLite structure/foreign keys, payload checksums,
indexed identities and job/event-history consistency. `JobRunner` checks existing
integrity before callback execution; the inspection CLI also verifies it. These
checks detect accidental corruption, not adversarial edits that recompute hashes.
Read-only mode uses SQLite's `mode=ro` and `query_only`; it creates neither a missing
database nor a writer lock and never migrates or repairs state.

## Current pilot integration

New runtime pilots record scope, request/attempt identity, job and events along
with their original started/completed receipts. Successful and known failed first
trial receipts remain readable through the existing command. Retries use distinct
jobs/requests and leave those receipts unchanged. Cached reads perform no model
contact. A new retry must match the run's immutable parameters and code identity;
changed code/configuration belongs to a new output folder.

Use the operations guide for the actual inspection/migration/retry commands.
No `pipeline run` command or scientific-stage execution is introduced by C05.