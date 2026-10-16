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
have typed schemas when configured. Encoder and prompt bindings remain reserved.
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
structure and dependencies; role outputs and handoff bindings follow there.
