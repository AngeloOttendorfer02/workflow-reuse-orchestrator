# Operations and current capabilities

Run these commands from the project root. Code verification and configuration
inspection use Python 3.12 and uv; model operations also require a running
Ollama service with an installed text-generation model.

## Install and verify

```powershell
uv sync --locked --group dev
uv run --locked --group dev ruff check .
uv run --locked --group dev ruff format --check .
uv run --locked --group dev mypy src
uv run --locked --group dev pytest -q
```

For automatic lint fixes and formatting:

```powershell
uv run --locked --group dev ruff check . --fix
uv run --locked --group dev ruff format .
```

Review changes and repeat verification after applying fixes.

## Check configuration and planned stages

```powershell
uv run --locked orchestrator pipeline check --config configs/study.yaml
uv run --locked orchestrator pipeline plan --config configs/study.yaml
```

Expected status is `foundations_ready`, with `runtime_check_available: true`
and `workflow_execution_available: false`. Model, inference, and request limits
have typed schemas when configured. Encoder and prompt declarations have schemas
but remain unbound in the draft configuration.
The linked scientific YAML files are drafts; full dataset, feature, and
statistical validation belongs to their work packages. All nine study stages
remain pending execution.

## Read model metadata

```powershell
uv run --locked orchestrator runtime models
$modelName = Read-Host "Paste an exact installed Ollama model name"
uv run --locked orchestrator runtime inspect --model $modelName
```

The model identifier is the exact installed name, including its tag. Metadata
inspection reads the server version, installed digest, native context,
tokenizer vocabulary fingerprint, template fingerprint, and model metadata
fingerprint. It performs no generation and updates no study settings.

The local endpoint defaults to `http://localhost:11434`. Override it using
`--base-url` or the shell environment:

```powershell
$env:OLLAMA_BASE_URL = "http://localhost:11434"
```

The application does not automatically load `.env` files.

## Run one infrastructure pilot

After choosing `$modelName`, use a fresh output folder:

```powershell
$pilotRun = "runs/model-check-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
uv run --locked orchestrator pipeline runtime-check --model $modelName --output $pilotRun --timeout-seconds 180
```

The pilot verifies current metadata and attempts one short generation. It
prints phase progress to stderr and the JSON result to stdout. Started and
completed receipts, model identity, inference controls, the prompt, budget,
usage, and response are stored in `$pilotRun/results.sqlite3`.

With no configured inference binding, the default pilot uses context 4096,
output cap 128, temperature 0, the study seed, and disabled thinking. These are
infrastructure-pilot controls. They do not establish final workflow limits or
change `configs/study.yaml`. Override context/output using `--num-ctx` and
`--num-predict`; an existing inference binding must agree with explicit options.

`status: passed` requires a measured generation with completion reason `stop`
and output equal to `OK` after trimming surrounding whitespace. Thinking tags
and extra response text fail the check. Raw response text and measured usage
remain recorded, including all extra output tokens. This does not establish
question-answering correctness or scientific readiness. Missing token counts,
missing completion reasons, and truncation also produce failed checks.
Host-observed and provider times use seconds. Failed generation attempts
consume the model-call allowance.

Reusing the same output and parameters reads the completed receipt with
`measurement_source: stored_receipt`; it makes no fresh provider call. A started
receipt without completion has an unknown outcome and blocks a silent retry.
A deliberately repeated measurement uses a new output folder and is counted
as another attempt.

Receipts from the previous pilot validator remain historical records. The
corrected validator refuses to reuse them; choose a new output folder.

## Accounting boundary

Use one `BudgetTracker` across all roles, planning, repair, attempted reuse,
and fallback. `BudgetedGenerator` binds one model/profile to that tracker.
Input reservations conservatively use the configured context size; output
reservations use the configured generation cap. Measured tokens reconcile those
reservations. Unknown token usage blocks further generation. Tools and failed
tool attempts consume their own allowance, and at most one fallback plan is
permitted.

HTTP timeouts bound I/O phases. The tracker checks the monotonic deadline before
and after effects; it records and fails a completed overrun. It does not claim
an exact interruption of a synchronous model call at the wall-time deadline.
Full prompt fitting and explicit handling of long passages/tables belong to
the agent/executor work package. Workflow declarations currently validate graph
structure, dependencies, typed role outputs and handoff bindings. Full workflow
execution remains a later work package.

## Acquire raw benchmark sources

C06 implements raw-source acquisition separately from normalization, source-role
assignment, scoring, and workflow execution. Inspect the configured source catalog
without contacting external services:

```powershell
uv run --locked --offline orchestrator data sources
```

Start with one small live source and repeat the same command to verify local reuse:

```powershell
uv run --locked orchestrator data acquire --dataset finqa --split dev
uv run --locked --offline orchestrator data acquire --dataset finqa --split dev
```

The second command verifies already-acquired source bytes without downloading.
`--offline` controls uv dependency resolution; it does not block application
networking if a requested raw source is missing.

Acquire every configured native split when sufficient disk space is available:

```powershell
uv run --locked orchestrator data acquire --dataset all
```

Choose `--dataset hotpotqa`, `--dataset drop`, or `--dataset finqa` for one dataset.
`--split train`, `--split dev`, or `--split test` selects a native split. DROP ships
train/dev together, so either request acquires the complete archive. An unsupported
split is rejected before downloads. Use `--raw-root` for an alternative source
directory and `--timeout-seconds` for the network I/O timeout.

Each release lives under `data/raw/<dataset>/<release>/`. Original source bytes
remain intact alongside one `acquisition.json` manifest: canonical source and
explicit mirror if configured, revision, license references, timestamps, checksums,
byte lengths, HTTP metadata, and native record/question counts. Final redirect URLs
omit query parameters. A kernel lock coordinates writers; the lock file can remain
on disk after completion.

Interrupted downloads retain `.part` bytes and checksummed checkpoints. Repeating
the command resumes a compatible byte range or safely restarts an incomplete
download if range resumption is unavailable. Completed-source corruption, changed
plans, and incorrect pinned hashes fail explicitly rather than overwriting a
completed release. Retain the original acquisition record when diagnosing failures.

HTTPS acquisition uses Python's default system CA certificates, including the
Windows CA and ROOT stores, with hostname and certificate verification enabled.
`SSL_CERT_FILE` and `SSL_CERT_DIR` can explicitly select a trusted CA bundle or
OpenSSL certificate directory. A `CERTIFICATE_VERIFY_FAILED` error can indicate
that an HTTPS inspection proxy or antivirus CA is missing from the trusted roots.
Use a CA approved by your network administrator; certificate verification must
remain enabled. After correcting certificate trust, repeat the acquisition command:
verified files are reused, and compatible partial downloads can resume.

FinQA dev alone reports the release as `partial` and its dev source as `complete`;
train and test are pending. The aggregate source checksum is available only after
the whole release is acquired and verified. Raw acquisition counts are separate
from later retained counts and executed experiment sizes. These commands make no
model calls, fit no selector, and do not update scientific snapshot bindings or pass
the prepared-data readiness gate.

## Normalize HotpotQA offline

After C06 acquisition, normalize both native splits from the project root:

```powershell
uv run --locked --offline orchestrator data normalize `
    --dataset hotpotqa `
    --output data/processed/hotpotqa-staging.sqlite3
```

This command makes no network/model calls and needs no Conda certificate override.
`--raw-root` defaults to `data/raw`. Relative input/output paths resolve against
the configured project root. Progress goes to stderr; stdout contains the final
machine-readable audit, normalization identity, and per-split counts.

Use `--split dev` or `--split train` to normalize one native split. Give a different
output path when selecting different splits, for example:

```powershell
uv run --locked --offline orchestrator data normalize `
    --dataset hotpotqa --split dev `
    --output data/processed/hotpotqa-dev-staging.sqlite3
```

Repeat the exact same command to verify reproducibility. It should report
`verified_existing` with the same `normalization_id` and unchanged file bytes.
The rerun re-verifies raw sources and regenerates the logical content before
checking the existing artifact. A file change, conflicting task ID, source-plan
mismatch, or output collision fails without replacing the existing output.

The SQLite file separates `inputs`, `evaluation_references`, `sources`,
`task_sources`, `provenance`, `exclusions`, and its metadata manifest. Use
`load_hotpotqa_task(path, task_id, split=...)` for model input and the explicitly
separate `load_hotpotqa_reference(...)` only for evaluator work. These package
functions are in `workflow_reuse_orchestrator.data.hotpotqa`. The staging artifact
does not enforce scientific-role access; final-pool references must not be used
to tune development decisions.

`scientific_roles_assigned`, `data_snapshot_available`, and
`study_bindings_updated` remain false. C11 assigns source-separated roles and C12
publishes the combined frozen snapshot after all adapters and scorer checks.
Raw and processed artifacts stay outside Git.
