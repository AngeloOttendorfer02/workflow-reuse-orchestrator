# Set up the new repository

This guide creates a separate `workflow-reuse-orchestrator` project alongside
the existing thesis repository. Keep the previous repository and any structure
backup folders. Do not copy its `.git`, `.venv`, old `uv.lock`, source tree, or
allocation notebooks into this starter.

## 1. Check the tools

Open PowerShell and run:

```powershell
git --version
uv --version
```

Both commands must succeed. uv uses the supplied `.python-version` to select
Python 3.12 and can install that interpreter when needed.

## 2. Extract the starter into a new sibling folder

Download `Workflow_Reuse_Orchestrator_Starter.zip` to your Downloads folder.
The ZIP contains one top-level folder: `workflow-reuse-orchestrator`.

```powershell
$thesisRoot = Join-Path $env:USERPROFILE "Desktop\FH_Master_AI\Master_Thesis"
$newProjectRoot = Join-Path $thesisRoot "workflow-reuse-orchestrator"
$starterZip = Join-Path $env:USERPROFILE "Downloads\Workflow_Reuse_Orchestrator_Starter.zip"

if (-not (Test-Path -LiteralPath $starterZip -PathType Leaf)) {
    throw "Starter ZIP not found: $starterZip"
}
if (-not (Test-Path -LiteralPath $thesisRoot -PathType Container)) {
    throw "Thesis folder not found: $thesisRoot"
}
if (Test-Path -LiteralPath $newProjectRoot) {
    throw "The new project folder already exists: $newProjectRoot"
}

Expand-Archive -LiteralPath $starterZip -DestinationPath $thesisRoot -ErrorAction Stop
Set-Location -LiteralPath $newProjectRoot -ErrorAction Stop
```

Adjust `$starterZip` or `$thesisRoot` if you saved the ZIP or thesis elsewhere.
These commands leave the old repository and its backups in place.

## 3. Install and inspect

```powershell
uv sync --locked --group dev
uv run --locked orchestrator --help
uv run --locked orchestrator pipeline check
uv run --locked orchestrator pipeline plan
```

The check must show `scaffold_ready`, `workflow_execution_available: false`,
and five pending bindings. The plan must list nine pending stages. No Ollama
server or dataset download is needed for the starter.

## 4. Run the development checks

```powershell
uv run --locked --group dev ruff check .
uv run --locked --group dev ruff format --check .
uv run --locked --group dev mypy src
uv run --locked --group dev pytest -q
```

Every command must pass before you proceed. See `docs/operations.md` for the
formatting commands if you edit the files.

## 5. Make the first commit

```powershell
git init -b main
git add .
git diff --cached --stat
git commit -m "chore: initialize workflow reuse project"
git status --short
```

Check the staged summary before committing. It should contain starter source,
configuration, notebooks, documentation, tests, and `uv.lock`. Generated data
and the virtual environment are ignored. After a successful commit, the final
status command should print nothing.

If Git requests an identity, configure your actual name and email for this
repository, then repeat the commit. Use values you intend to appear in Git
history.

## 6. Create the GitHub repository

In GitHub, create `workflow-reuse-orchestrator` under your account. Choose the
visibility you want. Leave the README, `.gitignore`, and license initialization
options unselected because you already have a local first commit. Copy the new
repository's HTTPS URL.

## 7. Connect and push

```powershell
$remoteUrl = Read-Host "Paste the HTTPS URL of your new GitHub repository"
git remote add origin $remoteUrl
git remote -v
git push -u origin main
```

Verify the displayed remote is the new repository before pushing. Complete
GitHub authentication if Git requests it. The old repository stays available
as the source archive; deletion is not part of this setup.

## Next implementation step

Adapt the reusable domain contracts, Ollama adapter, cumulative accounting,
calculator, SQLite receipts, checksums, and their relevant tests from the old
project. Revalidate model metadata on the actual machine. Old pilot receipts
are historical evidence, and short pilot limits are not final workflow limits.
Complete those foundations before dataset preparation and notebooks 01/02.
