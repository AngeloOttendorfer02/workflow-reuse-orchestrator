# Workflow Reuse Orchestrator: Commit Plan

Planning baseline: 16 October 2026
Project: Task-Adaptive Multi-Agent Reasoning: Workflow Reuse for Reliable and Efficient Problem Solving  
Author: Angelo Ottendorfer

This plan defines **60 proposed commits from the current repository to a finished,
reproducible thesis prototype and its experimental evidence**. Split a commit when
needed to keep a change reviewable; combine a measurement-only record when it has
no independent meaningful diff. Keep dependency gates and scientific controls intact.

## Governing academic timetable

| Institutional deadline | Deliverable / responsibility | Planned preparation and evidence |
| --- | --- | --- |
| 1 September 2026 | Supervisors assigned by the programme director. | Historical administrative checkpoint; do not assume assignment status from this plan. |
| 15 October 2026 | Proposal, five net pages, student to supervisor through Moodle. | Verify submission status because the date has passed at this planning baseline. Retain the submitted version. |
| Before the end of January 2027 | At least four short supervisor meetings, individually arranged. | Count meetings already held; plan remaining meetings across October-January and retain concise decisions/actions. |
| 1 December 2026 | Progress report extending the proposal, student to supervisor through Moodle. | Draft 23-25 November; review and finalize 26-30 November; submit by 1 December. |
| End of January 2027 | Intermediate defence before a panel, showing a significant first result, e.g. a working prototype. | Integrated development prototype target 17 January; evidence/rehearsal package target 24 January; confirm actual panel date. |
| 15 April 2027 | Master examination registration using the provided form to MAI administration. | Prepare by 8 April and submit by 15 April; retain confirmation. |
| 1 May 2027 | First complete thesis to the supervisor by email for feedback. | Complete draft target 25 April; consistency/proofreading buffer 26-30 April; send by 1 May. |
| 1 June 2027 | Final thesis upload through CIS, including plagiarism check. | Final text/artifacts target 28 May; verify required checks/format and upload by 1 June. |
| Approximately 5 June 2027 | Final thesis video through Moodle. | Prepare narrative/assets during May; final recording/check by 3 June; confirm actual deadline. |
| Approximately 10 June 2027 | AI Master Symposium, poster plus other fourth-term quality gates, at the Festsaal. | Prepare poster/demo during May; rehearsal and final materials by 7 June; confirm event and quality-gate details when announced. |
| End of June 2027 | Master defence/examination with a panel of three lecturers. | Preparation in May; focused presentation/Q&A rehearsal throughout June; confirm examination date. |
| Not specified | Graduation ceremony. | Follow the programme's announcement; no date is invented here. |

## Finished-product definition

The finished product is a local application that accepts a new question with
supplied passages/tables, chooses and executes a permitted collaboration, returns
an answer, and exposes the workflow, evidence, agent steps and cumulative resources.
It provides CLI and notebook entry points and a compact inspectable HTML report.
It does not require production hosting, authentication, multi-model routing or an
unbounded general-agent platform.

Research completion additionally requires:

- Three reproducible benchmark snapshots: HotpotQA distractor, DROP and FinQA.
- Five matched principal policy families, one fixed generative model and encoder.
- Validated generalized workflows, common up-to-three candidates, and one shared
  whole-request budget including planning, repairs, failed reuse and fallback.
- Four candidate predictor families, the versioned 140-feature interface and
  development-only fitting/calibration/selection.
- Main, feature ablation, three transfer, distinct-request volume, variability,
  candidate diagnostic and independent human-assessment evidence as registered.
- Frozen inputs/releases, complete outcomes and costs, registered statistical
  analysis, nine independent notebooks, reproducible figures and thesis materials.

## Common verification

From the project root for application changes:

```powershell
uv sync --locked --group dev
uv run --locked --group dev ruff check .
uv run --locked --group dev ruff format --check .
uv run --locked --group dev mypy src
uv run --locked --group dev pytest -q
uv run --locked orchestrator pipeline check --config configs/study.yaml
uv run --locked orchestrator pipeline plan --config configs/study.yaml
```

These are current setup/quality commands, not commands that execute the final study.
Do not add a live provider or full benchmark run to ordinary offline CI. Run targeted
boundary tests as the implementation changes; run the normal quality suite before
merging. Documentation-only changes require link/path and consistency review, not
new implementation-mirroring tests. Add future runtime/stage/freeze/report syntax to
operations only when the command actually exists.

## Revised phase overview

| Phase | Commits | Capability / gate | Internal target window |
| --- | --- | --- | --- |
| A: Reconcile project and foundations | C01-C05 | Integrate existing work, align the latest proposal, complete contracts/CI/early persistence. | 16-25 October 2026 |
| B: Prepare data and scoring | C06-C12 | Three canonical adapters, verified scorers, source-separated snapshot, notebooks 01/02. | 26 October-8 November 2026 |
| C: Build agents and baselines | C13-C18 | Encoder, bounded executor, inspected traces and measured single/fixed baselines. | 9-22 November 2026 |
| D: Planning and reusable library | C19-C23 | Fresh planning, independently validated main library, shared candidates and transfer-capable release machinery. | 23 November-13 December 2026; progress report in parallel before 1 December |
| E: Collect selector evidence | C24-C27 | Main candidate labels, audited 140-feature interface and fitting-only transformations. | 14 December 2026-3 January 2027; transfer collections follow in January/early February |
| F: Train predictors and variants | C28-C31 | Four-family main comparison and selected calibrated predictor; independent ablation/transfer assets. | C28-C30: 4-10 January 2027; C31 completion: 1-7 February |
| G: Integrate adaptive reuse | C32-C35 | Five policies, common fallback/accounting, notebook 08 and measured development comparison. | 11-17 January 2027; defence evidence/rehearsal by 24 January |
| H: Complete experiment/report software | C36-C40 | Registered families, statistics, report, robust multi-scope resume, finished demo interface. | Incremental throughout; main work 18 January-7 February 2027 |
| I: Feasibility and final-study freeze | C41-C44 | Measured final workload, protocol, immutable main/transfer releases and pre-final checks. | 8-14 February 2027 |
| J: Protected study | C45-C50 | Main/supplementary measurements, independent assessment and completeness audit. | 15 February-21 March 2027, with early capacity checks and contingency |
| K: Analysis | C51-C54 | Registered effects, all research questions, final notebook/report and thesis figures. | 22 March-4 April 2027 |
| L: Finish and reproduce | C55-C60 | Final docs/bundles, complete thesis, clean reproduction and named prototype release. | 5 April-28 May 2027; draft by 25 April, supervisor delivery by 1 May |
| Academic follow-through | Parallel writing/presentation checkpoints | Feedback, final upload, video, symposium/poster and examination. | May-June 2027; fixed/approximate deadlines above govern |

The January intermediate defence does not require the full protected study to be
finished. The prototype and its development results must already be real,
inspectable and reproducible. Final populations stay protected until the February
protocol/release gate. Do not describe a January pilot as final benchmark evidence.

## Calendar checkpoints and buffers

| By / period | Required state | Evidence to retain |
| --- | --- | --- |
| 25 October | Integrated foundations and scoped research plan. | Checked code revision, decisions, supervisor questions. |
| 8 November | Dataset/scorer/source-role pipeline. | Snapshot identity, count/leakage/scoring audit; notebooks 01/02. |
| 22 November | Measured role execution and baseline prototype. | Graph/answer/trace examples, development correctness/resources and limitations. |
| 25 November | Progress-report draft. | Updated problem/methods, actual completed work, first evidence, risks and remaining schedule. |
| 30 November | Progress report ready for the 1 December submission. | Reviewed report and submission checklist; workflow-library completion is not a prerequisite. |
| 13 December | Validated main library and common retrieval. | Admission/generalization evidence, startup costs, notebook 05. |
| 3 January | Main selector data ready for fitting. | Group/label/feature/rank audit and notebook 06. |
| 10 January | Main validation-selected predictor ready. | Four-family comparison, calibration, threshold/cost provenance. |
| 17 January | Adaptive prototype ready for demonstration. | Five-policy development run, bounded fallback, fresh-evidence example, notebook 08. |
| 24 January | Intermediate-defence package ready. | Recorded live-demo backup, first measured paired comparison, architecture slide and limitations; rehearsal. |
| Before the end of January | Intermediate defence and at least four meetings completed. | Actual panel/meeting dates and outcomes; no completed status is assumed. |
| 7 February | Required final experiment and variant machinery complete. | Main/transfer/ablation fitted assets and study-ready software. |
| 14 February | Final protocol and releases frozen. | Scoring/margins/samples/statistics/repetitions/human scope, hashes and gate checks. |
| 21 March | Registered experiments complete or explicit deviation/incompleteness decision. | Full family/request accounting, measurements and retained artifacts. |
| 4 April | Final analyses and thesis exports ready. | Registered tables/figures, uncertainty, errors, notebook 09 and report. |
| 8 April | Examination-registration paperwork prepared. | Required form/checklist; submit by 15 April. |
| 25 April | Complete thesis draft assembled. | All chapters, results, limitations, bibliography and figures; no missing-results placeholders. |
| 1 May | First complete version sent to supervisor. | Exact sent version and delivery record. |
| 2-23 May | Feedback and corrections. | Comment-resolution record, verified text/figure corrections and reproduction checks. |
| 28 May | Final submission package and prototype release ready. | Final thesis, artifact index, final checks and evidence identities. |
| 1 June | Final thesis upload/plagiarism workflow completed. | Submission/check receipts according to programme requirements. |
| Approximately 5/10 June | Video and symposium deliverables. | Final video, poster, demonstration and event-specific requirements. |
| End of June | Examination preparation and defence. | Talk, Q&A notes, final demo and actual confirmed examination date. |

## Commit index

| ID | Suggested commit subject | Depends on |
| --- | --- | --- |
| C01 | `chore: integrate existing runtime foundations with main` | Current repository |
| C02 | `refactor: align learned policy selection with the proposal` | C01 |
| C03 | `build: add offline checks and scientific configuration gates` | C02 |
| C04 | `feat: complete workflow bindings and shared request contracts` | C01, C03 |
| C05 | `feat: persist resumable study jobs and execution events` | C04 |
| C06 | `feat: acquire versioned benchmark sources with provenance` | C03, C05 |
| C07 | `feat: normalize HotpotQA distractor inputs and references` | C04, C06 |
| C08 | `feat: normalize DROP passages and typed answers` | C04, C06 |
| C09 | `feat: normalize FinQA reports tables and evaluator programs` | C04, C06 |
| C10 | `feat: verify dataset scorers and binary success rules` | C07, C08, C09 |
| C11 | `feat: assign source-grouped development and final roles` | C07, C08, C09, C10 |
| C12 | `feat: publish canonical dataset snapshots and data notebooks` | C05, C10, C11 |
| C13 | `feat: add a pinned encoder and representation cache` | C03, C12 |
| C14 | `feat: implement structured agent roles and tool loops` | C04, C05, C12 |
| C15 | `feat: execute workflow graphs with cumulative limits` | C04, C05, C14 |
| C16 | `feat: inspect request graphs evidence and resource traces` | C05, C15 |
| C17 | `feat: add single-agent and fixed-workflow baselines` | C10, C15 |
| C18 | `feat: run measured baseline pilots and document feasibility` | C12, C13, C16, C17 |
| C19 | `feat: plan and repair bounded question-specific workflows` | C14, C15, C18 |
| C20 | `feat: collect discovery traces with complete startup accounting` | C05, C10, C11, C19 |
| C21 | `feat: generalize and independently validate reusable workflows` | C10, C20 |
| C22 | `feat: retrieve common eligible workflow candidates` | C13, C21 |
| C23 | `feat: publish main and transfer library releases` | C11, C20, C21, C22 |
| C24 | `feat: collect matched candidate-success observations` | C10, C11, C15, C23 |
| C25 | `feat: define the versioned 140-feature interface` | C13, C22, C24 |
| C26 | `feat: fit representation transforms on training groups only` | C25 |
| C27 | `feat: audit selector datasets and complete feature notebook` | C24, C25, C26 |
| C28 | `feat: compare four success predictors with grouped validation` | C02, C27 |
| C29 | `feat: calibrate success scores and tune suitability costs` | C27, C28 |
| C30 | `feat: load validation-selected predictors for inference only` | C28, C29 |
| C31 | `feat: train feature ablations and independent transfer selectors` | C23, C27, C28, C29, C30 |
| C32 | `feat: add similarity-based workflow reuse` | C17, C19, C22, C29 |
| C33 | `feat: add prediction-based workflow reuse` | C22, C30, C32 |
| C34 | `feat: enforce common bounded fallback and method parity` | C15, C19, C32, C33 |
| C35 | `feat: run the complete adaptive development pipeline` | C12, C18, C23, C30, C34 |
| C36 | `feat: register complete experiment families and sampling` | C23, C30, C35 |
| C37 | `feat: implement registered statistics and resource accounting` | C10, C24, C36 |
| C38 | `feat: generate compact reports and shared research figures` | C16, C35, C37 |
| C39 | `feat: harden multi-scope resume and stage progress` | C05, C35, C36, C38 |
| C40 | `feat: provide a reference-free question demo and inspection CLI` | C16, C34, C38, C39 |
| C41 | `docs: record measured workload and study feasibility` | C35, C36, C37, C39 |
| C42 | `docs: freeze the protected evaluation protocol` | C10, C36, C37, C41 |
| C43 | `feat: publish immutable main and transfer releases` | C23, C30, C31, C42 |
| C44 | `test: verify the frozen study from entry point to report` | C35, C38, C39, C40, C43 |
| C45 | `docs: record the frozen principal-method experiment` | C42, C43, C44 |
| C46 | `docs: record the registered feature-ablation experiment` | C31, C36, C43, C44 |
| C47 | `docs: record leave-one-dataset-out transfer experiments` | C23, C31, C36, C43, C44 |
| C48 | `docs: record variability diagnostics and independent assessments` | C36, C42, C43, C44 |
| C49 | `docs: record startup amortization and request-volume evidence` | C36, C41, C45, C47 |
| C50 | `docs: reconcile protected study completeness and deviations` | C45, C46, C47, C48, C49 |
| C51 | `feat: produce registered main effects and correctness gates` | C37, C50 |
| C52 | `feat: summarize predictor ablation transfer and volume analyses` | C31, C37, C49, C50 |
| C53 | `docs: analyze human agreement and trace-based failure patterns` | C48, C50, C51, C52 |
| C54 | `feat: complete final-results notebook and thesis exports` | C38, C51, C52, C53 |
| C55 | `docs: finalize setup usage limitations and reproduction guidance` | C40, C50, C54 |
| C56 | `feat: export reproducible workflow and selector bundles` | C43, C54, C55 |
| C57 | `docs: assemble thesis methods results and discussion materials` | C50, C51, C52, C53, C54 |
| C58 | `test: verify clean-checkout reproduction and final demo` | C44, C54, C55, C56 |
| C59 | `chore: prepare submission-ready research artifacts` | C55, C56, C57, C58 |
| C60 | `chore: finalize the thesis prototype release` | C59 |

## Detailed commit specifications

Paths below are relative to the repository. Under `domain/`, `runtime/`, `data/`,
`workflows/`, `learning/`, `evaluation/`, `experiments/` and `reporting/`, paths
refer to `src/workflow_reuse_orchestrator/`. Notebook basenames refer to
`notebooks/`; test names refer to `tests/`.

### Phase A: Reconcile the project and foundations

**Target gate:** Existing work integrated; latest proposal/configuration aligned; contracts, CI and early persistence ready.

#### C01 — `chore: integrate existing runtime foundations with main`

**Internal target:** 16-25 October 2026  
**Type:** implementation  
**Depends on:** Current repository  
**Main files/areas:** Existing runtime-foundations branch; domain/, runtime/, storage.py, CLI/configuration/tests; README and operations status.

**Work:** Inspect the uploaded Git graph and local differences before changing anything. Preserve local work in a verified backup or separate reviewed commit. Integrate the existing runtime-foundations change while retaining the expanded planning documentation. Resolve code/dependency/example conflicts together, and update status prose to describe the integrated implementation. Do not replace main with the old branch or repeat its implementation. Use a normal merge commit when conflict reconciliation is needed; the suggested subject may be the merge subject.

**Accepted when:** The existing model/provider contracts, budgets, calculator/search helpers, receipt store, model inspection, and short infrastructure check are on main and pass their relevant checks. Documentation changes remain. No unexplained local changes are included. A real runtime check is identified as an infrastructure check, not workflow readiness.

#### C02 — `refactor: align learned policy selection with the proposal`

**Internal target:** 16-25 October 2026  
**Type:** implementation  
**Depends on:** C01  
**Main files/areas:** README.md; docs/research_plan.md, methods.md, decisions.md, implementation_plan.md; configs/study.yaml, learning.yaml; config/CLI tests.

**Work:** Align the research question and four proposal subquestions. Add random forest to logistic regression, gradient boosting, and MLP comparisons. Make the principal learned policy predictor-neutral, with the predictor selected using development validation. Migrate the hard-coded prediction-reuse-mlp method ID to a documented generic prediction-reuse identity; preserve explicit historical IDs in old receipts. Keep the current two-layer MLP as a declared starting candidate architecture rather than the predetermined winner. Freeze the model-selection rule before final results.

**Accepted when:** Proposal, prose, configuration schemas, method IDs, and CLI tests agree. All five policy families remain. Historical identifiers are interpretable, and no final-outcome-based predictor choice is possible.

#### C03 — `build: add offline checks and scientific configuration gates`

**Internal target:** 16-25 October 2026  
**Type:** implementation  
**Depends on:** C02  
**Main files/areas:** pyproject.toml, uv.lock, .github/workflows/ci.yml; config.py and configuration tests.

**Work:** Add CI for Python 3.12 using the locked development environment, lint, formatting, typing, and offline tests. Establish typed dataset/learning/evaluation configuration ownership incrementally. Separate scaffold-valid, runtime-bound, data-ready, and protected-release-ready validation. Draft nulls are permitted only at stages that do not require them. External provider tests remain opt-in.

**Accepted when:** A clean checkout runs offline checks without Ollama or datasets. Invalid or cross-owned settings fail clearly. A configuration check cannot falsely certify final readiness.

#### C04 — `feat: complete workflow bindings and shared request contracts`

**Internal target:** 16-25 October 2026  
**Type:** implementation  
**Depends on:** C01, C03  
**Main files/areas:** domain/tasks.py, workflows.py, outcomes.py, budgets.py, providers.py; runtime/budgets.py, tools.py; contract/unit tests.

**Work:** Extend existing contracts with typed node input/output/evidence bindings, role outputs, attempt/failure states, and observable metadata. Keep evaluator references separately loaded. Harden DAG validation and whole-request allowance behavior, including unknown usage, tool/repair/fallback limits, and remaining-time handling. Review the existing restricted calculator and supplied-source search instead of creating competing implementations.

**Accepted when:** Invalid graph/binding/reference leakage cases fail before model/tool effects. Existing basic graph and budget tests remain valid; multi-attempt accounting and missing measurements have explicit semantics.

#### C05 — `feat: persist resumable study jobs and execution events`

**Internal target:** 16-25 October 2026  
**Type:** implementation  
**Depends on:** C04  
**Main files/areas:** storage.py; experiments/stages.py and pipeline.py; storage/resume integration tests.

**Work:** Extend the existing versioned receipt/artifact store with queryable run, scope, stage, job, request, attempt, and event identities. Record intent before calls and results atomically afterward. Implement completed-job resume, unknown-effect handling, writer locking, integrity checks, and explicit retry identities. Expose basic phase/count/usage progress immediately. Version schema changes without silently reinterpreting old databases.

**Accepted when:** A deterministic interrupted run resumes known work without duplicate completed effects. Unknown external calls remain unknown with possible cost; retries are explicit. Read-only inspection cannot mutate the run and startup receipts have method/fold lineage.

### Phase B: Prepare data and scoring

**Target gate:** Three canonical adapters, verified scorers, source-separated snapshot, notebooks 01/02.

#### C06 — `feat: acquire versioned benchmark sources with provenance`

**Internal target:** 26 October-8 November 2026  
**Type:** implementation  
**Depends on:** C03, C05  
**Main files/areas:** data/prepare.py; configs/datasets.yaml; acquisition fixtures/tests.

**Work:** Define acquisition for the three released sources, content checksums, release/source locations, licensing metadata, raw split identities, and resumable downloads. Preserve original bytes. Record full acquisition counts separately from executed sample sizes. Add only necessary data dependencies with their lockfile changes.

**Accepted when:** Pinned fixture sources round-trip with verified hashes and provenance; missing/changed releases fail clearly. Re-acquisition does not overwrite a different source silently. A small live acquisition validates the route when explicitly run.

#### C07 — `feat: normalize HotpotQA distractor inputs and references`

**Internal target:** 26 October-8 November 2026  
**Type:** implementation  
**Depends on:** C04, C06  
**Main files/areas:** data/hotpotqa.py; task contracts; document/scoring fixtures.

**Work:** Preserve each question, supplied paragraphs, sentence boundaries, titles/source identities, answer alternatives, and support annotations. Separate model-facing context from evaluator-only support/reference fields. Reconcile raw, duplicate, malformed, and retained counts. Do not use gold supporting facts to select evidence.

**Accepted when:** Realistic fixtures retain distractors and sentence locations, use stable task/source IDs, and exclude answer/support fields from model input serialization.

#### C08 — `feat: normalize DROP passages and typed answers`

**Internal target:** 26 October-8 November 2026  
**Type:** implementation  
**Depends on:** C04, C06  
**Main files/areas:** data/drop.py; DROP fixtures and document preparation tests.

**Work:** Preserve passage identity, question, spans, number/date/multi-span answer types, alternate answers, and raw provenance. Maintain units and formatting for later numerical parsing. Specify malformed-record handling with counts.

**Accepted when:** Fixtures cover the supported answer types and multiple questions sharing one passage. Agent inputs are reference-free and canonical records round-trip without lossy flattening.

#### C09 — `feat: normalize FinQA reports tables and evaluator programs`

**Internal target:** 26 October-8 November 2026  
**Type:** implementation  
**Depends on:** C04, C06  
**Main files/areas:** data/finqa.py; table/cell contracts and fixtures.

**Work:** Preserve report/page grouping, surrounding text, headers, row/cell locations, number strings/units, question IDs, and native splits. Store answers and gold programs in evaluator-only records. Do not substitute gold selected evidence for the supplied report context.

**Accepted when:** A calculation can point back to the original text/cells; programs/answers never reach online input. Shared report/page relationships and retained/excluded counts are reproducible.

#### C10 — `feat: verify dataset scorers and binary success rules`

**Internal target:** 26 October-8 November 2026  
**Type:** implementation  
**Depends on:** C07, C08, C09  
**Main files/areas:** evaluation/scoring.py; configs/evaluation.yaml; test_dataset_answer_scoring.py.

**Work:** Implement pinned HotpotQA/DROP answer EM and F1 behavior and FinQA numeric correctness. Specify output parsing, alternate references, span matching, percentage/unit treatment, tolerance, invalid/truncated outputs, and binary-label criteria. Use reviewed fixtures including disagreement/edge cases. Record evaluator identity before any label collection.

**Accepted when:** Scorer fixtures agree with the pinned dataset-specific rules. Confirmed execution/output failures are incorrect, partial F1 is not silently binary success, and future label collection binds a scorer version.

#### C11 — `feat: assign source-grouped development and final roles`

**Internal target:** 26 October-8 November 2026  
**Type:** implementation  
**Depends on:** C07, C08, C09, C10  
**Main files/areas:** data/splits.py; configs/datasets.yaml; test_source_partition_contract.py.

**Work:** Build source-equivalence relations and connected components, including aliases/duplicates and cross-dataset overlap. Audit giant components before assigning discovery, independent library validation, fitting, validation, calibration, and final roles. Reserve the proposal final source pools and remove documented development overlap. Define infeasibility resolution before collection; prepare leave-one-dataset-out scope exclusions.

**Accepted when:** No forbidden source component crosses scientific roles. Counts/components/overlap exclusions reconcile. A large HotpotQA component blocks unsafe splitting rather than being broken invisibly; actual role sizes are justified by the audit.

#### C12 — `feat: publish canonical dataset snapshots and data notebooks`

**Internal target:** 26 October-8 November 2026  
**Type:** implementation  
**Depends on:** C05, C10, C11  
**Main files/areas:** data/prepare.py; dataset SQLite/manifest handling; notebooks/01_data_overview.ipynb and 02_data_preparation.ipynb.

**Work:** Publish a checksummed datasets.sqlite3 snapshot with separately loaded inputs/references, source relationships and assignments. Add the implemented data stage to the shared pipeline/CLI. Populate notebooks 01/02 with package calls for development EDA, tables, context tails, grouping, exclusions, and scoring audits. Final labels are not exploratory tuning material.

**Accepted when:** Snapshot regeneration and read-only loading are reproducible. Both notebooks run independently from explicit artifacts and inspect measured development data. CLI checks distinguish data-ready from scaffold-ready.

### Phase C: Build measurable agents and baselines

**Target gate:** Pinned encoder, bounded shared executor, two baselines, inspected real development traces.

#### C13 — `feat: add a pinned encoder and representation cache`

**Internal target:** 9-22 November 2026; measured baseline evidence ready for the December report  
**Type:** implementation  
**Depends on:** C03, C12  
**Main files/areas:** runtime/encoder.py; encoder binding/configuration; representation tests and dependencies.

**Work:** Bind immutable encoder/tokenizer revisions. Define task/context/workflow serialization, chunking, pooling, vector normalization, and length behavior. Cache by content and binding hashes. Use development examples for feasibility; no final representation fitting. Pin evidence serialization consistently across later methods.

**Accepted when:** Same binding/input produces matching vectors, changed serialization invalidates cache, and context overflow has an explicit recorded rule. Unknown encoder/model identities cannot enter a protected release.

#### C14 — `feat: implement structured agent roles and tool loops`

**Internal target:** 9-22 November 2026; measured baseline evidence ready for the December report  
**Type:** implementation  
**Depends on:** C04, C05, C12  
**Main files/areas:** workflows/agents.py; configs/prompts/*.md; role/tool tests.

**Work:** Implement coordinator, retrieval, reasoning, and checking output schemas and versioned prompts through one role runner. Add bounded supplied-evidence search and calculator requests. Validate evidence locations and typed tool inputs. Charge output repairs and tool loops to the request; generalization remains an offline coordinator operation.

**Accepted when:** Mock role executions produce contract-valid outputs using current evidence. Tool effects, malformed responses, checker pass/fail/uncertain states, and costs are recorded without evaluator access.

#### C15 — `feat: execute workflow graphs with cumulative limits`

**Internal target:** 9-22 November 2026; measured baseline evidence ready for the December report  
**Type:** implementation  
**Depends on:** C04, C05, C14  
**Main files/areas:** workflows/execution.py; graph/budget/e2e fixtures.

**Work:** Execute deterministic topological order and typed predecessor bindings through the shared runtime. Begin with sequential independent nodes. Validate each output, propagate declared failures, preserve partial answers/evidence and usage, enforce remaining limits before each effect, and designate the final answer consistently.

**Accepted when:** Fixtures cover fan-in, cycles, missing bindings, failed tools, exhausted budgets, and interruption. No node/fallback creates an independent allowance or silently ignores earlier cost.

#### C16 — `feat: inspect request graphs evidence and resource traces`

**Internal target:** 9-22 November 2026; measured baseline evidence ready for the December report  
**Type:** implementation  
**Depends on:** C05, C15  
**Main files/areas:** reporting/queries.py; CLI request inspection; notebook 03_agent_execution.ipynb.

**Work:** Provide read-only request/attempt/node queries and a graph/timeline/evidence view. Surface per-role calls/tokens, missing telemetry, errors and cumulative use. Populate notebook 03 from a persisted development trace and a diagnosed limit/failure example. Use concise structured intermediate outputs rather than requiring private model reasoning.

**Accepted when:** A request can be inspected without generation or fitting; source references resolve and displayed resource totals equal stored attempt totals. Notebook 03 is independently executable.

#### C17 — `feat: add single-agent and fixed-workflow baselines`

**Internal target:** 9-22 November 2026; measured baseline evidence ready for the December report  
**Type:** implementation  
**Depends on:** C10, C15  
**Main files/areas:** workflows/policies.py; baseline definitions/configuration; policy tests.

**Work:** Implement the tool-using single agent and development-selected fixed graph with equivalent evidence, tools, answer contract, model controls and request ceilings. Declare their repair behavior and prohibit hidden planner fallback. Persist policy identity and any fixed-graph development selection cost.

**Accepted when:** Paired fixtures show both policies use the common runtime/evaluator. Agent count is not treated as call count; fixed structure stays fixed while evidence changes per question.

#### C18 — `feat: run measured baseline pilots and document feasibility`

**Internal target:** 9-22 November 2026; measured baseline evidence ready for the December report  
**Type:** measurement-backed implementation  
**Depends on:** C12, C13, C16, C17  
**Main files/areas:** experiments/pipeline.py and stages.py; runtime/config bindings; notebook 04_baselines_and_planning.ipynb.

**Work:** Add a representative development pilot across the three datasets, long contexts, table questions, and failure cases. Verify target-machine model identity and observed CPU/GPU/runtime behavior. Measure token/context/output/time needs and establish pilot request ceilings. Populate the first baseline portion of notebook 04; keep pilot receipts outside Git.

**Accepted when:** Measured limits and context handling have documented development evidence. Warm-up/cache/load policy is explicit. Infrastructure smoke limits are not reused as final workflow limits. Expensive discovery remains blocked if feasibility is unresolved.

### Phase D: Plan and validate reusable workflows

**Target gate:** Fresh-planning baseline and frozen independently validated main/transfer libraries.

#### C19 — `feat: plan and repair bounded question-specific workflows`

**Internal target:** 23 November-13 December 2026; main library first, transfer collections gated per scope  
**Type:** implementation  
**Depends on:** C14, C15, C18  
**Main files/areas:** workflows/planning.py and policies.py; coordinator prompt; planning tests and notebook 04.

**Work:** Implement per-question planning and the finite malformed-plan repair policy. Include planner/repair usage in the shared budget, validate before execution and preserve failed plans. Extend baseline comparisons and notebook 04 using matched development questions.

**Accepted when:** Fresh planning is a complete measurable baseline; invalid/oversized/cyclic graphs never execute, planner failures remain in denominators, and all planning/repair cost is visible.

#### C20 — `feat: collect discovery traces with complete startup accounting`

**Internal target:** 23 November-13 December 2026; main library first, transfer collections gated per scope  
**Type:** implementation  
**Depends on:** C05, C10, C11, C19  
**Main files/areas:** workflows/library.py; discovery stage/subphases; startup receipt queries.

**Work:** Schedule permitted discovery questions under explicit main/transfer scopes. Persist successful and unsuccessful plans/executions with scorer and source-group lineage. Identify procedural role/dependency patterns as generalization candidates and retain every attempted effect in startup totals.

**Accepted when:** Discovery cannot read final-role inputs/references or a held-out transfer dataset. Failed/discarded traces remain accounted for and can be inspected/restarted under explicit attempt identities.

#### C21 — `feat: generalize and independently validate reusable workflows`

**Internal target:** 23 November-13 December 2026; main library first, transfer collections gated per scope  
**Type:** implementation  
**Depends on:** C10, C20  
**Main files/areas:** workflows/library.py; generalization prompt; library contract tests.

**Work:** Generalize successful procedures by removing example-specific entities/values/answers and evidence locations; canonicalize and deduplicate. Execute templates on independent library-validation groups. Apply documented development admission/support/diversity limits, preserve provenance and rejection reasons, and test changed-evidence behavior.

**Accepted when:** No procedure is admitted from discovery success alone. Templates execute on new evidence, contamination checks pass, and admitted/rejected/generalization/validation costs all reconcile.

#### C22 — `feat: retrieve common eligible workflow candidates`

**Internal target:** 23 November-13 December 2026; main library first, transfer collections gated per scope  
**Type:** implementation  
**Depends on:** C13, C21  
**Main files/areas:** workflows/library.py; candidate retrieval/serialization tests.

**Work:** Build the frozen library index and retrieve up to three eligible templates using cosine similarity and deterministic identity ties. Separate procedure retrieval from within-question evidence search. Store candidate IDs, similarities, eligibility and empty-set reasons for reuse-policy parity.

**Accepted when:** Both reuse families receive identical candidate sets for identical input/library bindings. Retrieval has no gold dependency; cache/index changes require new bound identities.

#### C23 — `feat: publish main and transfer library releases`

**Internal target:** 23 November-13 December 2026; main library first, transfer collections gated per scope  
**Type:** measurement-backed implementation  
**Depends on:** C11, C20, C21, C22  
**Main files/areas:** experiments/definitions.py and library release storage; notebook 05_workflow_library.ipynb.

**Work:** Publish the main library first and implement three independent leave-one-dataset-out library scopes using the same pipeline. Construct/freeze each transfer library before collecting that fold's selector labels, with full transfer construction allowed to continue in January/early February. Freeze admission rules and procedure/index content before the corresponding selector labeling. Populate notebook 05 with generalization, validation support, coverage, retrieval examples, and complete startup costs.

**Accepted when:** The main library is ready for January integration. Scope-exclusion tests and release machinery work; every transfer library, when constructed, excludes its target dataset from construction/admission lineage. All transfer libraries are frozen before their fold's collection/fitting and the February final-release gate. Frozen hashes prevent drift; notebook 05 labels unavailable versus measured fold artifacts honestly.

### Phase E: Collect and audit selector evidence

**Target gate:** Matched labeled candidates and fitting-only 140-feature interface with audited lineage.

#### C24 — `feat: collect matched candidate-success observations`

**Internal target:** 14 December 2026-3 January 2027 for main scope; transfer evidence completed before fold fitting  
**Type:** implementation  
**Depends on:** C10, C11, C15, C23  
**Main files/areas:** learning/examples.py; collect_candidates stage; candidate outcome tests.

**Work:** Execute every eligible common candidate in the registered development collection, with separate training/validation/calibration roles and fold IDs. Complete the main scope first for the January prototype; run transfer collections only after the relevant fold library is frozen and before fitting that fold. Record positives, confirmed negatives, all-zero candidate sets, unknown effects, costs and scorer versions. Candidate collection itself is startup work, not a free offline label source.

**Accepted when:** Rows reconcile task/candidate/attempt identities and source roles; no final/held-out transfer examples enter development. Unknown interrupted outcomes are not invented labels and retries preserve prior possible cost.

#### C25 — `feat: define the versioned 140-feature interface`

**Internal target:** 14 December 2026-3 January 2027 for main scope; transfer evidence completed before fold fitting  
**Type:** implementation  
**Depends on:** C13, C22, C24  
**Main files/areas:** learning/features.py; configs/learning.yaml; selector feature tests.

**Work:** Define 64 task and 64 workflow representation slots, four task metadata values, six graph metadata values and two compatibility scores. Pin units/counting/serialization including context length, numbers, table headers, depth and handoffs. Exclude dataset IDs, golds, current cost and checker outcomes.

**Accepted when:** Exactly 140 named ordered columns are produced under one schema. Feature provenance is pre-execution; training and request-time raw feature definitions agree on fixtures.

#### C26 — `feat: fit representation transforms on training groups only`

**Internal target:** 14 December 2026-3 January 2027 for main scope; transfer evidence completed before fold fitting  
**Type:** implementation  
**Depends on:** C25  
**Main files/areas:** learning/features.py; transformation persistence and parity tests.

**Work:** Fit reductions/scaling/imputation only on selector-fitting data and permitted library representations. Define effective-rank limits and zero-padding when fewer than 64 independent components exist; distinguish padding from missing measurements. Save full state and use the same inference transformation path.

**Accepted when:** Altering held-out inputs cannot change fitted transforms. Effective rank is reported, transformed feature order is stable, and reload parity holds without adding validation vectors to fit PCA.

#### C27 — `feat: audit selector datasets and complete feature notebook`

**Internal target:** 14 December 2026-3 January 2027 for main scope; transfer evidence completed before fold fitting  
**Type:** implementation  
**Depends on:** C24, C25, C26  
**Main files/areas:** learning/examples.py and audit queries; notebook 06_selector_data_and_features.ipynb.

**Work:** Audit class/group support, duplicates, source isolation, library lineage, all-zero sets, unknowns, telemetry, rank and feature leakage for main and transfer scopes. Declare one-class/insufficient-support handling and freeze training/validation/calibration/threshold-role assignments. Populate notebook 06 with actual audit outputs.

**Accepted when:** Training is blocked on unsupported or contaminated data. An auditable checksummed main population and transformation lineage exist for January fitting; the same audit is mandatory per transfer scope before its later fitting. Notebook 06 explains denominators/missingness without hiding hard cases.

### Phase F: Fit and select the success predictor

**Target gate:** Four predictor families compared; calibrated selected model, ablations, transfer fitted state.

#### C28 — `feat: compare four success predictors with grouped validation`

**Internal target:** 4-10 January 2027 for the main development selector  
**Type:** implementation  
**Depends on:** C02, C27  
**Main files/areas:** learning/training.py; learning search configuration; predictor tests/dependencies.

**Work:** Implement logistic regression, random forest, histogram gradient boosting, and MLP under one pipeline and matched features/examples. Bound tuning budgets, seeds, regularization/class handling, iteration limits and stopping. Use external source-grouped validation; prevent hidden random early-stopping splits. Start MLP with the declared two-layer candidate unless revised on development evidence.

**Accepted when:** Four candidate families have reproducible fit receipts, validation MCC/Brier/overhead comparisons, and complete preprocessing lineage. Model selection does not access final outcomes; failed/unsupported fits have explicit reasons.

#### C29 — `feat: calibrate success scores and tune suitability costs`

**Internal target:** 4-10 January 2027 for the main development selector  
**Type:** implementation  
**Depends on:** C27, C28  
**Main files/areas:** learning/training.py and selection.py; configs/learning.yaml; calibration/selection fixtures.

**Work:** Fit the chosen calibration on its declared role, select probability and similarity thresholds using permitted development data, and create candidate token-cost estimates from development executions. Define a structure-based estimate fallback for sparse cost observations as allowed by the proposal. Tune the declared correctness/coverage/resource rule without using current-task observed cost.

**Accepted when:** Reliability/Brier diagnostics, threshold trade-offs, estimated-cost error, sparse-data behavior and all tuning lineage are recorded. Stable tie rules and no-candidate behavior are testable.

#### C30 — `feat: load validation-selected predictors for inference only`

**Internal target:** 4-10 January 2027 for the main development selector  
**Type:** implementation  
**Depends on:** C28, C29  
**Main files/areas:** learning/selection.py; selector artifacts and integrity tests; generic policy configuration.

**Work:** Apply the predeclared model-selection rule using validation quality, calibration and overhead; persist the selected family plus alternatives. Save and load transforms, model, calibration, feature schema, thresholds and cost estimator together. Keep fitting imports/operations out of protected request execution.

**Accepted when:** Selected family is explicit and may be LR/RF/GBT/MLP. Loaded features/probabilities/decisions match in-memory results, altered hashes fail, and inference cannot fit or silently retune state.

#### C31 — `feat: train feature ablations and independent transfer selectors`

**Internal target:** Main notebook section by 17 January; full ablation/transfer assets 1-7 February 2027  
**Type:** measurement-backed implementation  
**Depends on:** C23, C27, C28, C29, C30  
**Main files/areas:** learning/training.py; experiment scopes; notebook 07_selector_training.ipynb.

**Work:** Refit/retune variants without six graph metadata values (134), four task metadata values (136), and both (130), retaining embeddings. Register whether ablations hold the selected predictor family fixed to isolate features; any retuned-family variant is separate. Build transfer-fitted state with target exclusion through transformations, fitting, calibration, thresholds and costs. Populate the main predictor section of notebook 07 for January; complete the ablation/transfer sections with their measured artifacts in early February. C31's complete supplementary assets are a February freeze gate, not a prerequisite for C35's January main-prototype demonstration.

**Accepted when:** Every main/ablation/transfer artifact has scope-correct lineage. Feature attribution claims acknowledge information remaining in embeddings. Notebook 07 reports four-family selection and external validation evidence.

### Phase G: Integrate adaptive reuse

**Target gate:** All five policies, common fallback/accounting, complete development pipeline and notebook 08.

#### C32 — `feat: add similarity-based workflow reuse`

**Internal target:** 11-17 January 2027; defence evidence/rehearsal package by 24 January  
**Type:** implementation  
**Depends on:** C17, C19, C22, C29  
**Main files/areas:** workflows/policies.py; reuse policy tests.

**Work:** Select the highest-similarity eligible candidate passing its frozen rule. Execute fresh evidence through the common executor and emit candidate/selection reasons. Use the common fallback boundary rather than implementing a second recovery engine.

**Accepted when:** Similarity selection matches the declared threshold/tie behavior, uses the same common candidate set, and never returns cached discovery answers.

#### C33 — `feat: add prediction-based workflow reuse`

**Internal target:** 11-17 January 2027; defence evidence/rehearsal package by 24 January  
**Type:** implementation  
**Depends on:** C22, C30, C32  
**Main files/areas:** workflows/policies.py; learning/selection.py; selector-policy integration tests.

**Work:** Predict calibrated candidate success, keep candidates above the threshold, and select minimum estimated token use with a stable identity tie. Load the validation-selected predictor through the generic learned method ID. Record probability/cost/qualification explanations and selection overhead.

**Accepted when:** Only pre-execution values drive selection. Changing references or observed candidate outcomes cannot change the online decision; generic learned policy works with every supported frozen predictor family.

#### C34 — `feat: enforce common bounded fallback and method parity`

**Internal target:** 11-17 January 2027; defence evidence/rehearsal package by 24 January  
**Type:** implementation  
**Depends on:** C15, C19, C32, C33  
**Main files/areas:** workflows/policies.py and execution.py; shared-budget/recovery integration tests.

**Work:** Implement one fresh fallback plan for no qualifying candidate or frozen detectable-failure/checker triggers. Specify uncertain-verdict behavior and recoverable failure codes. Charge rejected/failed reuse, planning repairs and fallback to the original allowance; preserve undetected wrong answers. Verify single/fixed policies have no hidden planner escape.

**Accepted when:** Matched policy tests prove candidate parity, evidence/tool/budget equivalence, at most one fallback, and no gold-triggered recovery. All failed attempts remain in correctness/resource accounting.

#### C35 — `feat: run the complete adaptive development pipeline`

**Internal target:** 11-17 January 2027; defence evidence/rehearsal package by 24 January  
**Type:** implementation  
**Depends on:** C12, C18, C23, C30, C34  
**Main files/areas:** experiments/pipeline.py and stages.py; shared CLI API; notebook 08_complete_pipeline.ipynb.

**Work:** Expose supported development stage/full-run operations with explicit run/snapshot/scope IDs. Complete nine-stage wiring without allowing a development run to launch final evaluation automatically. Run all five policies on a representative development set and populate notebook 08 with candidates, selection, execution, fallback and totals. Produce the January significant-first-result evidence and a saved demonstration backup. Use the main library/selector without requiring completion of full transfer and ablation assets; preserve final populations for protected evaluation.

**Accepted when:** A complete request and matched development comparison execute via CLI and package calls. Notebook 08 is independently reproducible and clearly labels live versus stored receipts.

### Phase H: Complete experiment and reporting software

**Target gate:** Registered family execution, statistics, compact reporting, robust progress/resume and demo.

#### C36 — `feat: register complete experiment families and sampling`

**Internal target:** Incremental earlier delivery; complete final-study support 18 January-7 February 2027  
**Type:** implementation  
**Depends on:** C23, C30, C35  
**Main files/areas:** experiments/definitions.py; configs/evaluation.yaml; experiment-definition tests.

**Work:** Define principal, predictor, feature-ablation, transfer, distinct-request volume, three-repetition subset, candidate diagnostics and blinded human-assessment scopes. Register predictor-comparison development versus supplementary live scope. Assign group-aware samples, stable fold/repetition IDs, output populations and method order; design assessor packets before final outcomes.

**Accepted when:** Each required proposal question maps to executable jobs and declared populations; unsupported live/replay claims cannot be mixed. Transfer uses independent releases and all extra diagnostic costs have separate categories.

#### C37 — `feat: implement registered statistics and resource accounting`

**Internal target:** Incremental earlier delivery; complete final-study support 18 January-7 February 2027  
**Type:** implementation  
**Depends on:** C10, C24, C36  
**Main files/areas:** evaluation/statistics.py; analytical fixtures; reporting query contracts.

**Work:** Implement paired source-group bootstrap intervals, correctness-loss gates, registered paired tests, effect sizes and Holm families. Define within-dataset question-weighted accuracy, relative ratio-of-total resource reductions, macro summaries and unknown-data sensitivity. Separate deployment startup/serving totals from total research expenditure and keep tokens/calls/time distinct.

**Accepted when:** Small analytical fixtures verify grouping/pairing, failure denominators, gate direction, multiplicity, unavailable measurements and cost reconciliation. Statistical settings can be frozen before protected runs.

#### C38 — `feat: generate compact reports and shared research figures`

**Internal target:** Incremental earlier delivery; complete final-study support 18 January-7 February 2027  
**Type:** implementation  
**Depends on:** C16, C35, C37  
**Main files/areas:** reporting/queries.py, plots.py, report.py, templates/report.html; report fixtures.

**Work:** Generate results.sqlite3-backed metrics.csv and report.html with scope/dataset/method/fold, N, units, coverage and interval identities. Include progress/completeness, correctness/resources, candidate/reuse/fallback, startup and selected trace views. Share plotting functions with notebooks; avoid embedding all prompts/outputs into one enormous page.

**Accepted when:** Reports regenerate read-only from receipts and reconcile with query totals. Small/failed/incomplete runs are usable and missing values are not displayed as zero or experimental success.

#### C39 — `feat: harden multi-scope resume and stage progress`

**Internal target:** Incremental earlier delivery; complete final-study support 18 January-7 February 2027  
**Type:** implementation  
**Depends on:** C05, C35, C36, C38  
**Main files/areas:** experiments/stages.py and storage.py; interruption/concurrency integration tests.

**Work:** Extend the early resume/progress foundation to complete method/fold/repetition job matrices. Display fitting/validation/calibration/threshold subphases and discovery/generalization/validation phases separately. Add plan-versus-completion reconciliation, writer-conflict handling and intentional retry inspection across large runs.

**Accepted when:** Simulated crashes at several stage/effect boundaries preserve completed work and unknown cost. Stage/method/fold counts reconcile without re-running fitted or generated work under changed bindings.

#### C40 — `feat: provide a reference-free question demo and inspection CLI`

**Internal target:** Incremental earlier delivery; complete final-study support 18 January-7 February 2027  
**Type:** implementation  
**Depends on:** C16, C34, C38, C39  
**Main files/areas:** cli.py; examples/document_question.json; operations documentation and demo tests.

**Work:** Expose a bounded supplied-document question operation using a frozen development release plus read-only request inspection and report regeneration. Validate a useful reference-free example with table/evidence locations. Show graph/role steps, answer and resources through CLI/HTML; do not add hosting/authentication to meet a local-prototype requirement.

**Accepted when:** A new input can be answered and inspected without gold annotations, training, or library mutation. Supported syntax is documented, unavailable future commands are not advertised as working.

### Phase I: Measure feasibility and freeze

**Target gate:** Feasible protocol and samples, immutable main/transfer releases, pre-final end-to-end checks.

#### C41 — `docs: record measured workload and study feasibility`

**Internal target:** 8-14 February 2027; before any protected final outcomes  
**Type:** measurement and protocol  
**Depends on:** C35, C36, C37, C39  
**Main files/areas:** configs/evaluation.yaml; docs/evaluation.md and decisions.md; measured pilot summary.

**Work:** Measure representative main/fold/library/candidate/training/reuse/fallback workloads and project all required families, storage and hardware time. Reconcile provisional final-pool counts. Choose full final execution or a documented source-grouped sample using feasibility and precision, with no arbitrary 3000-task cap. Revise provisional dates if measurements require it.

**Accepted when:** Estimated calls/tokens/time/storage include startup, transfer, ablations and repetitions; assumptions and uncertainty are stated. Final sample/scope choices are justified before final outcomes, and infeasible full-run promises are removed.

#### C42 — `docs: freeze the protected evaluation protocol`

**Internal target:** 8-14 February 2027; before any protected final outcomes  
**Type:** protocol  
**Depends on:** C10, C36, C37, C41  
**Main files/areas:** configs/evaluation.yaml and datasets.yaml; docs/evaluation.md and decisions.md.

**Work:** Fix dataset-specific acceptable correctness loss, primary comparisons/endpoints, confidence level/bootstrap/test/multiplicity rules, samples/seeds/order/cache/warm-up, repetitions, human rubric/sample/assessor blinding, diagnostics and failure/unknown/retry rules. Freeze which family is selected and which ablation model family is held fixed. Resolve all final-required null values.

**Accepted when:** The protocol has a dated pre-outcome identity and an executable job specification. Margins have a substantive rationale, not a choice made to obtain significance. Human agreement is measured before reconciliation.

#### C43 — `feat: publish immutable main and transfer releases`

**Internal target:** 8-14 February 2027; before any protected final outcomes  
**Type:** implementation  
**Depends on:** C23, C30, C31, C42  
**Main files/areas:** experiments/freeze.py; release export/verification; frozen-release integration tests.

**Work:** Bind code/lockfile, data/role hashes, model/encoder, prompts/tools, limits, libraries, transformations, predictors/calibration, thresholds/costs, scoring/statistics and execution conditions into immutable main/transfer releases. Validate completeness and allowed lineage. Protect final mode from fitting, admission, threshold mutation or changed data.

**Accepted when:** Incomplete/incompatible/tampered assets are refused before expensive effects. Release load produces the same predictions/decisions, and each fold excludes its target from all development lineage.

#### C44 — `test: verify the frozen study from entry point to report`

**Internal target:** 8-14 February 2027; before any protected final outcomes  
**Type:** implementation  
**Depends on:** C35, C38, C39, C40, C43  
**Main files/areas:** e2e/integration/notebook smoke tests; fixture runs; supported operations instructions.

**Work:** Run the entire registered control path on deterministic small fixtures and a bounded live development smoke population: setup, preparation loading, release validation, five methods, fallback, resume, scoring and report. Smoke-test notebooks independently; confirm analysis/report paths do not generate or fit. Use no protected final outcomes for debugging.

**Accepted when:** A reviewed study-ready code revision and release identity pass targeted checks and the normal quality suite. Protected data stays unopened for performance analysis until the frozen protocol is ready.

### Phase J: Run and account for the protected study

**Target gate:** Main/supplementary measurements with completeness, blinded assessment and deviation record.

#### C45 — `docs: record the frozen principal-method experiment`

**Internal target:** 15 February-21 March 2027 under the frozen protocol  
**Type:** experiment execution and results documentation  
**Depends on:** C42, C43, C44  
**Main files/areas:** docs/results.md (new consolidated results record); final run provenance links/identities.

**Work:** Execute the five-policy main study on the registered identical final questions. Use progress/resume and retain all outcomes/costs. Commit only a compact provenance/completeness summary with code/release/snapshot/run IDs and durable artifact hashes; run databases and raw traces remain outside Git. No threshold/model changes follow the results.

**Accepted when:** Every main planned request is accounted for; paired identities and measured resource coverage reconcile. Incomplete/unknown effects are disclosed and no advantage is claimed before registered analysis.

#### C46 — `docs: record the registered feature-ablation experiment`

**Internal target:** 15 February-21 March 2027 under the frozen protocol  
**Type:** experiment execution and results documentation  
**Depends on:** C31, C36, C43, C44  
**Main files/areas:** docs/results.md; ablation protocol identities and outcome provenance.

**Work:** Execute the registered feature-ablation live population or explicitly scoped diagnostic evaluation using its frozen refitted variants. Keep candidate/library/evidence/budget controls matched. Distinguish fixed-family feature effects from any supplementary model-family reselection.

**Accepted when:** The 140/134/136/130 comparisons have declared populations, predictor-family controls, complete costs and inspectable provenance. Replay-only results are not labeled live latency evidence.

#### C47 — `docs: record leave-one-dataset-out transfer experiments`

**Internal target:** 15 February-21 March 2027 under the frozen protocol  
**Type:** experiment execution and results documentation  
**Depends on:** C23, C31, C36, C43, C44  
**Main files/areas:** docs/results.md; three fold release/run identities.

**Work:** Execute each target dataset using its independently developed release. Verify exclusions before execution; report retrieval coverage, candidate prediction quality and policy correctness/resources within the registered target scope. Charge fold-specific startup work and keep main/transfer interpretation separate.

**Accepted when:** All three target folds are represented with exact permitted development lineage. No main-trained transformation/library/threshold is quietly substituted, and failures count in target results.

#### C48 — `docs: record variability diagnostics and independent assessments`

**Internal target:** 15 February-21 March 2027 under the frozen protocol  
**Type:** experiment execution and results documentation  
**Depends on:** C36, C42, C43, C44  
**Main files/areas:** docs/results.md; repetition/diagnostic/assessment provenance.

**Work:** Run the three repetitions and extra candidate measurements on their preselected subsets. Deliver blinded packets to the two independent assessors through the agreed study process, preserve initial ratings and compute agreement/kappa before reconciliation. Record sampling/reconciliation rules and extra research costs. No automated sending is implied by this plan.

**Accepted when:** Repetitions are identifiable rather than pooled as independent source groups. Initial ratings and agreement precede reconciled outcomes; candidate diagnostics remain hindsight evidence and have separately charged costs.

#### C49 — `docs: record startup amortization and request-volume evidence`

**Internal target:** 15 February-21 March 2027 under the frozen protocol  
**Type:** measurement and results documentation  
**Depends on:** C36, C41, C45, C47  
**Main files/areas:** docs/results.md; cost aggregation/query outputs and volume sequence identities.

**Work:** Use predeclared distinct request sequences and actual method-required startup/serving records to compute cumulative tokens/calls/time. Separate common infrastructure, method-specific startup and total research expense. If additional registered live request sequences are required, execute them; label stored-record aggregation honestly. Do not count repeated cached answers as new-request savings.

**Accepted when:** Volume curves and any break-even point reconcile to traces and meet the correctness condition. No-crossing/insufficient-range outcomes are stated. Training time is never added to tokens or invented currency/energy.

#### C50 — `docs: reconcile protected study completeness and deviations`

**Internal target:** 15 February-21 March 2027 under the frozen protocol  
**Type:** study audit  
**Depends on:** C45, C46, C47, C48, C49  
**Main files/areas:** docs/results.md and decisions.md; completeness/deviation queries.

**Work:** Audit all family/task/method/fold/repetition counts, unknown effects, resource missingness, evaluator versions and release integrity. Resolve permitted retries or report incomplete populations and sensitivity bounds. Record deviations with dates and affected results; a substantive post-outcome method change creates a new clearly separated study.

**Accepted when:** The study is either complete under the registered protocol or explicitly labeled incomplete with consequences. There is no silent successful-only subset, overwritten release or missing failed-startup expenditure.

### Phase K: Analyze the results

**Target gate:** Registered effects, uncertainty, all research-question analyses and final notebook/report.

#### C51 — `feat: produce registered main effects and correctness gates`

**Internal target:** 22 March-4 April 2027  
**Type:** analysis and tested reporting  
**Depends on:** C37, C50  
**Main files/areas:** evaluation/statistics.py and reporting queries where needed; docs/results.md.

**Work:** Apply the preregistered paired source-group analysis to dataset correctness, calls/tokens/end-to-end time and primary comparisons. Report effects, uncertainty, multiplicity treatment, sample/group support and missing-data impact. Use percentage points for absolute correctness differences and clear resource denominators.

**Accepted when:** Claims follow the fixed loss gate and statistical rule; datasets with failed gates are reported as trade-offs. Numerical outputs trace to frozen records and registered calculations, with no result-driven endpoint changes.

#### C52 — `feat: summarize predictor ablation transfer and volume analyses`

**Internal target:** 22 March-4 April 2027  
**Type:** analysis and tested reporting  
**Depends on:** C31, C37, C49, C50  
**Main files/areas:** reporting/queries.py and plots.py; docs/results.md.

**Work:** Produce four-family predictor comparisons, reliability/MCC/Brier, explicit-metadata ablations, transfer changes and startup-volume plots. Separate development model-selection evidence from final candidate diagnostics and distinguish no-benefit, sparse-support and unamortized-startup outcomes.

**Accepted when:** Comparisons use declared matched populations; effective ranks, model-family choices, overhead and fold lineage are visible. Offline replay is not interpreted as measured unseen execution behavior.

#### C53 — `docs: analyze human agreement and trace-based failure patterns`

**Internal target:** 22 March-4 April 2027  
**Type:** analysis and documentation  
**Depends on:** C48, C50, C51, C52  
**Main files/areas:** docs/results.md; read-only trace queries/figures if needed.

**Work:** Analyze pre-reconciliation agreement, reconciled supplementary ratings, and sampled failure traces. Classify retrieval/selection mistakes, evidence gaps, arithmetic/units, invalid graphs, checker errors, resource exhaustion, fallback overhead and template contamination. Discuss benchmark/model/pretraining and scorer limits.

**Accepted when:** Each explanation is backed by identifiable records and sampling context, with no selective anecdotes replacing aggregate evidence. No final release is retrained based on the error analysis.

#### C54 — `feat: complete final-results notebook and thesis exports`

**Internal target:** 22 March-4 April 2027  
**Type:** implementation  
**Depends on:** C38, C51, C52, C53  
**Main files/areas:** notebook 09_final_results.ipynb; reporting/plots.py and report.py.

**Work:** Populate notebook 09 with read-only final analysis, correctness intervals/gates, resource distributions, predictor/ablation/transfer/volume figures, variability, agreement and errors. Generate the final compact report and deliberate publication-quality figure/table exports from shared queries.

**Accepted when:** Notebook and HTML/CSV figures agree on values, scope and denominators. A rerun performs no generation/fitting, labels final/pilot/replay correctly and reproduces every thesis-facing export.

### Phase L: Finish, reproduce and release

**Target gate:** Final documentation, artifacts, thesis materials, clean reproduction and named prototype release.

#### C55 — `docs: finalize setup usage limitations and reproduction guidance`

**Internal target:** 5-11 April 2027; refine supported usage during May feedback  
**Type:** implementation  
**Depends on:** C40, C50, C54  
**Main files/areas:** README.md, SETUP.md, docs/operations.md, architecture.md, project_structure.md and decisions.md.

**Work:** Replace starter-only status and outdated setup/first-commit guidance with actual supported commands. Document installation, required hardware/runtime, source acquisition, snapshot/release restoration, development versus final modes, resume, question demo, inspection/report regeneration and known limitations. Reconcile final architecture/config ownership and open decisions.

**Accepted when:** A reader can identify what runs, what remains out of scope, which measurements support claims and how to reproduce them. All local links/paths and command examples are checked.

#### C56 — `feat: export reproducible workflow and selector bundles`

**Internal target:** 5-18 April 2027; before independent final reproduction  
**Type:** implementation  
**Depends on:** C43, C54, C55  
**Main files/areas:** experiments/freeze.py and deliberate artifact export/import; packaging tests.

**Work:** Finish portable export/import around the existing frozen release: checksummed library/index, transforms, selected predictor, calibration, prompts/settings and reproduction manifest. Document exact external data/model dependencies and trusted local artifact-loading constraints. Include measured results as deliberate artifacts, never implicit raw files in every commit.

**Accepted when:** An exported bundle reloads into an independent run with parity and clear missing-dependency errors. Hashes and environment bindings are verified; generated caches/results are not accidentally tracked.

#### C57 — `docs: assemble thesis methods results and discussion materials`

**Internal target:** Writing throughout; complete draft by 25 April, supervisor delivery by 1 May 2027  
**Type:** thesis deliverable  
**Depends on:** C50, C51, C52, C53, C54  
**Main files/areas:** Thesis source where maintained; docs/results.md and named figure/table references.

**Work:** Assemble the complete thesis from the chapters drafted throughout October-March. Complete research-design/data/methodology descriptions from actual frozen choices; assemble result tables/figures and limitations; answer the proposal main question and four subquestions. Target the full draft by 25 April and supervisor delivery by 1 May; incorporate feedback through May without changing frozen scientific claims silently. Record deviations from the plan and null/negative outcomes. Keep the formal thesis in its designated writing source rather than duplicating full chapters across repository docs.

**Accepted when:** Every reported result has a run/release/query or exported-figure identity. Statements distinguish hypotheses, implementation, observations and limitations; no unmeasured production or generalization claim appears.

#### C58 — `test: verify clean-checkout reproduction and final demo`

**Internal target:** 19-25 April 2027; targeted recheck after material May corrections  
**Type:** implementation  
**Depends on:** C44, C54, C55, C56  
**Main files/areas:** Reproduction/e2e/notebook checks; operations validation evidence.

**Work:** Use a clean checkout and locked environment to restore declared snapshots/releases, reproduce features/predictions/scoring/figures from stored outcomes and run the bounded new-question demonstration. Execute each notebook independently under its documented inspection/smoke mode. Do not rerun the entire expensive final study merely to regenerate a report.

**Accepted when:** Independent setup reproduces numerical analytical outputs and loaded decisions; any fresh-generation nondeterminism is documented. No hidden notebook state, local path, cache or undeclared file is required.

#### C59 — `chore: prepare submission-ready research artifacts`

**Internal target:** 17-23 May 2027; final package ready by 28 May for the 1 June upload  
**Type:** implementation  
**Depends on:** C55, C56, C57, C58  
**Main files/areas:** Version metadata and README artifact index; final reproduction documentation.

**Work:** Reconcile deliverables: prototype, libraries, selected predictor, locked configurations, retained data/run artifacts, nine notebooks, report/CSV, thesis figures, writing materials and demo instructions. Check links, archive contents, notebook outputs and generated-file exclusions. Verify examination registration by 15 April, complete-draft delivery by 1 May and the final upload/plagiarism requirements by 1 June. Prepare the video/poster/defence materials in the parallel academic stream. Resolve submission-format/access requirements using the actual institution guidance; retain real delivery confirmations rather than claiming an action occurred because a commit exists.

**Accepted when:** Every promised deliverable is locatable, attributable to a code/release identity and available in the agreed artifact location. Required checks pass and limitations/deviations remain visible.

#### C60 — `chore: finalize the thesis prototype release`

**Internal target:** 24-28 May 2027; June academic deliveries follow separately  
**Type:** release  
**Depends on:** C59  
**Main files/areas:** Final release metadata, changelog/README status and artifact index.

**Work:** Target the final reproducible code/artifact state by 28 May, before the 1 June thesis upload. Commit that state and mark remaining optional extensions explicitly. Video, symposium and examination delivery continue on their academic deadlines in June; later presentation-only updates do not retune the frozen experiment. Create an annotated release tag after the commit using a version name appropriate to the delivered prototype, and associate the immutable evidence artifacts. Tagging/publishing is a separate operation, not an empty extra implementation commit or a claim of scientific superiority.

**Accepted when:** The named release resolves to the verified code and artifact identities; the finished product can answer and inspect new supplied-document questions and reproduce the registered study analyses. Final benefits or trade-offs are stated exactly as measured.

## Research-question and notebook traceability

| Proposal question | Implementation | Measurement and analysis |
| --- | --- | --- |
| Main: efficiency while maintaining correctness | C17-C19, C32-C35, C37-C44 | C45, C49-C51, C54 |
| RQ1: learned versus similarity selection | C22, C24-C30, C32-C34 | C45, C48, C51-C53 |
| RQ2: task/workflow metadata | C25-C27, C31 | C46, C52 |
| RQ3: dataset-excluded transfer | C11, C20-C24, C27-C31, C43 | C47, C52-C53 |
| RQ4: total startup and request-volume cost | C05, C18, C20-C24, C28-C29, C37 | C41, C49-C52 |

| Notebook | Main completion commit | Inputs |
| --- | --- | --- |
| 01 Data overview | C12 | Versioned sources and permitted development snapshot. |
| 02 Data preparation | C12 | Canonical inputs, scorer and source-role audit. |
| 03 Agent execution | C16 | Persisted measured role/executor traces. |
| 04 Baselines and planning | C19 | C18 baseline and C19 fresh-planning development receipts. |
| 05 Workflow library | C23; transfer sections completed before February freeze | Generalization, independent admission and retrieval evidence; main scope first. |
| 06 Selector data/features | C27 | Candidate outcomes, features, transforms and audit. |
| 07 Selector training | Main results by 17 January; C31 variants by 7 February | Four-family fits, calibration, threshold and scoped variants. |
| 08 Complete pipeline | C35 | Integrated five-policy development run. |
| 09 Final results | C54 | Complete frozen study and registered analytical queries. |

Each notebook loads persisted identities and runs without another notebook's kernel
state. Keep algorithms, acquisition, fitting, grouping and plotting in the package.
Default inspection should not generate/fine-tune models. Fixtures remain labeled
fixtures; they never substitute for missing scientific measurements.

## Scientific gates that must not be skipped

| Gate | Required before | Decisions that cannot be deferred |
| --- | --- | --- |
| Source and scoring gate | Discovery/candidate labels | Versions, normalization, binary success, source-equivalence and compatible scientific roles. |
| Runtime feasibility gate | Expensive discovery/collection | Model/encoder identity, context serialization, evidence access and full workflow ceilings. |
| Library gate | Candidate label collection | Independent admission, templates without discovery answers, frozen candidates and main/transfer lineage. |
| Training gate | Fitting/calibration | Grouped roles, 140-feature meaning/order, fitting-only transforms, class/rank support and tuning budget. |
| Validation-selection gate | Integrated protected release | Predictor-family selection, calibration, thresholds, token estimates and generic method identity. |
| Protocol gate | Final outcome inspection | Margins, samples, comparisons, statistics, repetitions, human/diagnostic scope, cache/order and failure rules. |
| Evidence completeness gate | Final conclusions | Paired population reconciliation, missing measurements, unknown effects, deviations and preserved artifacts. |

Library-validation, fitting, validation, calibration and final roles must remain
separate at source-group level. Final public source pools are provisional until
release/count/overlap audits; full acquisition does not mandate full execution.
The proposal's planned 18,088 final questions imply 90,440 principal requests for
five methods, before node-level calls and supplementary work. Do not project this
from the earlier one-call/128-output-token infrastructure check.

In transfer folds, remove the target dataset from discovery through validation,
calibration, thresholds, cost estimates and representation fitting. Keep a separate
release and startup account. A final checker sees observable sources and outputs,
not reference answers; an incorrect but undetected answer cannot trigger recovery.

## Work locations and evidence retention

Use the laptop for offline development, fixtures, preparation where storage permits,
and inspection. Use the execution PC for measured generation and long experiments.
Keep the locked code/environment and immutable snapshot/release IDs aligned across
machines; do not infer GPU acceleration from the device model alone.

Commit code/configuration, small fixtures, notebooks, docs and compact result
provenance. Retain raw sources, prepared databases, run databases, model/encoder
assets and deliberate exports in their agreed durable artifact location. Git tags
alone cannot preserve ignored experimental outputs. Track content checksums and
code/release/run identities so another machine can restore the evidence.

Use `results.sqlite3`, `metrics.csv` and `report.html` for ordinary run outputs.
Snapshots and frozen bundles are separate explicitly versioned inputs/exports.
Do not generate a directory of per-task JSON reports or duplicate notebook
implementations. A final artifact index should point to the retained evidence
without committing large files or exposing private machine settings.

## Scope control

Core requirements are the five policy families, four predictor comparisons, three
datasets, bounded reusable workflows, registered study, nine notebooks and local
inspection/reproduction. Optional extensions include hosted interfaces, arbitrary
external tool ecosystems, new datasets, online library mutation, multi-model
routing and additional live predictor policies. They do not block the core thesis.

Do not silently cut a proposal-required experiment when workload is high. Resolve
scope with a dated protocol decision before final outcomes and record its impact
on the research questions. A missed correctness gate, poor transfer or no observed
break-even is reported plainly rather than fixed by tuning on final results.
