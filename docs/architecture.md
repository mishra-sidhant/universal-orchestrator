# Architecture

Universal Orchestrator is arranged around the same planes as the source report.

## Host Plane

Hosts normalize their invocation into `HostInvocation`. The current CLI creates this object directly. Future adapters should preserve the same shape for Codex MCP, Claude Code slash commands, Cursor, VS Code, Windsurf, API, and CI.

Core model:

- `HostInvocation`
- `InputAttachment`
- `UserOptions`

The repo now includes a dependency-light stdio JSON-RPC/MCP-style adapter in `universal_orchestrator.mcp`. It exposes:

- `ai_team.run`
- `ai_team.status`
- `ai_team.artifacts`
- `ai_team.providers`
- `ai_team.doctor`
- `ai_team.configure`
- `ai_team.cancel`
- `ai_team.resume`
- `ai_team.evals`

`ai_team.status` now includes the runtime snapshot, and `ai_team.cancel` writes a durable cancellation request unless the run is already terminal. `ai_team.evals` can either list the built-in suite or execute it and write `eval_report.json`.

## Ingestion Plane

The ingestion plane inventories everything the user supplies, but does not assume every input should enter model context. It fingerprints files, extracts and redacts bounded source text, detects type, scans for secrets and instruction-like untrusted content, and emits a `ContextManifest`.

Implemented now:

- Prompt ingestion.
- Text, Markdown, code, and unknown text-like files.
- PDF text extraction through `pdfplumber` when available.
- Folder and repository scans with dependency/build/cache ignores.
- DOCX paragraph/table extraction through `python-docx` when available.
- PPTX slide and notes extraction through `python-pptx` when available.
- CSV/TSV and XLSX sampling through the standard library and `openpyxl` when available.
- Image metadata extraction through Pillow when available.
- Archive inventory for ZIP/TAR without unpacking, including path traversal warnings.
- URL/API inventory without network fetch by default; permission-gated fetch is available.
- Binary metadata records for remaining media and unknown formats.

Planned:

- OCR, archive sandbox extraction, API schema inference, and audio/video transcription.

## Context Intelligence Plane

Context intelligence converts `InputRecord` values into `ContextCard` objects, ranks them against the prompt, and creates `ContextPack` values for task-specific execution.

Current ranking is deterministic lexical overlap plus specificity and risk boosts. The system also writes a context index, conflict markers, and cache metadata for reuse and auditability. Future ranking should add embeddings, recency, trust, freshness, authority, and deeper semantic deduplication.

Context chunk IDs are stable across equivalent runs, carry source/line/page/slide/sheet locators, and are ranked into per-task packs. Provenance records bind those chunks back to source names and URIs:

- `context_chunks.json`
- `context_provenance.json`
- `context_packs.json`

## Product Plane

The `ProductContractCompiler` converts messy prompts into a `ProductContract` and `DefinitionOfDone`. This is the source of truth for planning and validation.

The first compiler infers:

- Run type.
- Requested output.
- Primary and secondary artifacts.
- Must-have constraints.
- Must-not-have constraints.
- Artifact and validation gates.

`ApprovalGateEngine` writes `approval_report.json` for internet access, repo writes, shell execution, and cloud provider execution. `PolicyCompiler` then creates `policy_report.json`; both the router and executor enforce it. Network fetch and hosted-model authority are separate decisions, and `local_only` always blocks hosted models.

## Orchestrator Kernel

The kernel uses `PlannerEnsemble` to create a five-node typed `TaskDAG`: context aggregation, gap analysis, extractive synthesis, static artifact construction, and quality evaluation. Every node maps to a concrete function in `StageWorkerRegistry`.

Each run writes `plan_review.json` with strategic, decomposition, risk, cost, and skeptic views. Their scores derive from contract artifact coverage, registered-worker coverage, dependency coverage, quality-stage coverage, cache safety, and actual cost tiers; no role has a hardcoded score.

Plan review includes critical path analysis, cost-tier estimation, batch simulation, and residual risks. The current real DAG is linear and truthfully reports max parallelism of one.

The DAG is validated for missing dependencies and cycles before routing.

Part B adds `BudgetController` and `DeltaPlanner`:

- `budget_report.json` records per-task token estimates, effective cost caps, and estimated spend.
- `delta_execution_plan.json` compares the run against the previous successful run and marks tasks reusable only when inputs are unchanged and the scheduler cache entry exists.

## Routing Plane

`CapabilityRegistry` describes providers by capability, cost tier, health, context limits, and kind. `AdaptiveRouter` selects the best available provider or marks a task as degraded, reshaped, or paused.

Current providers:

- `deterministic.tools`: always available local tools.
- `openai.configured`: enabled only when `OPENAI_API_KEY` exists.
- `anthropic.configured`: enabled only when `ANTHROPIC_API_KEY` exists.
- `ollama.local`: enabled only when `OLLAMA_BASE_URL` exists.

No hosted provider calls are made in this milestone.

Part B adds `routing_telemetry.json`, which records every provider considered for every task, including health status, capability score, cost score, total score, eligibility, and rejection reasons.

## Execution Plane

`StageWorkerRegistry` dispatches local DAG nodes to real functions and records structured outputs. Missing handlers return `SKIPPED`. `DeterministicExecutor` remains the dry-run provider-adapter boundary for future provider-backed tasks, but its generic local adapter never reports completion.

`DAGScheduler` executes real stage tasks by dependency-ready batches, records every attempt, enforces retry and timeout policies, skips dependents after failure, honors durable cancellation, uses versioned cache entries, and writes `schedule_report.json`. It reports cached and executed results through the same observer path. Side-effecting artifact/quality nodes are non-cacheable.

Task cache keys include context, contract, execution policy, provider descriptors, and routing decisions. Malformed entries are quarantined, and cached results are treated as successful product fragments. Delta planning compares against the most relevant prior successful run by input-hash similarity.

Part C adds `RepoValidationRunner`, which writes `repo_validation_report.json`. It detects repo test commands from repo maps, executes only allowlisted commands when `allow_shell` is true, and otherwise records the exact skipped validation plan.

## Quality Plane

`QualityGateEngine` checks:

- Manifest completeness.
- DAG validity.
- Routing coverage.
- Pauses, reshapes, degraded work, skipped tasks, and failed tasks.
- Partial parsing.
- High-severity security findings.
- Artifact existence.

When quality fails, `RepairPlanner` creates a targeted repair DAG from the specific violations, routes it through the same provider layer, executes repair tasks, writes repair artifacts, and re-runs quality. The validator registry now emits structured `ValidationFinding` records for manifest, contract, DAG, routing, execution, and artifact checks.

`EvidenceAuditor` writes `evidence_audit.json`. A claim resolves only when every cited chunk exists and appears in the exact context pack delivered to that task. Empty packs remain unsupported, valid-but-unconsumed refs fail audit, and final Sources include only refs from resolved claims. `citation_support` measures this consumed-reference coverage; it does not claim semantic entailment or factuality. All score formulas are documented in `docs/quality-metrics.md`.

Part C feeds `RepoValidationRunner` into quality scoring: failed executed repo validation becomes a violation, while unapproved shell execution is surfaced as a warning.

## Artifact Plane

`ArtifactStore` writes one run directory per run under `.uo/runs/{run_id}`. A final product owner assembles the user-facing package, rejects thin fragments, and writes `product_package.json` plus `final_report.md`. When requested, artifact builders create and validate PDF/DOCX outputs.

Repository runs produce an explicitly labeled plan rather than pretending deterministic analysis edited the repository:

- `patch_plan.md` and `patch_plan_validation.json` for repo implementation or patch-requested runs.
- `delivery_bundle.zip` and `zip_validation.json` for every run.
- `artifact_integrity_report.json`, which recomputes hashes and sizes before finalization.
- `checksums.json` and `delivery_receipt.json`, which bind the frozen manifest and ZIP to immutable hashes.

Finalization is one-way: payload artifacts, trace/debug reports, integrity audit, one-time run manifest, checksums, ZIP, ZIP validation, then delivery receipt. The manifest never hashes or rewrites itself. The ZIP includes the frozen manifest, checksums, trace, debug manifest, and integrity report.

Each package includes:

- `context_manifest.json`
- `context_cards.json`
- `context_index.json`
- `product_contract.json`
- `approval_report.json`
- `policy_report.json`
- `task_dag.json`
- `plan_review.json`
- `budget_report.json`
- `delta_execution_plan.json`
- `routing_decisions.json`
- `routing_telemetry.json`
- `execution_results.json`
- `schedule_report.json`
- `repo_validation_report.json`
- `validation_findings.json`
- `evidence_audit.json`
- `product_package.json`
- `quality_report.json`
- `delivery_bundle.zip`
- `zip_validation.json`
- `artifact_integrity_report.json`
- `checksums.json`
- `delivery_receipt.json`
- `trace_report.json`
- `debug_bundle_manifest.json`
- `final_report.md`
- `run_manifest.json`

When requested, packages can also include:

- `final_report.pdf`
- `pdf_validation.json`
- `final_report.docx`
- `docx_validation.json`
- `patch_plan.md`
- `patch_plan_validation.json`

When repair is triggered, packages also include:

- `repair_task_dag.json`
- `repair_execution_results.json`

## Runtime And Evaluation

`RuntimeStore` writes SQLite event and run-summary records under the artifact root. This is the first durable-state layer for resumability, audit, cancellation, and dashboard support.

Part A extends runtime durability with state transitions, task records, and resumable snapshots. Each run persists task status, attempt count, cache key, and lifecycle state transitions.

Runtime durability includes state transitions, attempt and failure records, cancellation requests, terminal-state-aware cancellation rejection, status snapshots, and same-run resume from the persisted `run_request.json`.

The optional FastAPI daemon exposes artifacts, status, cancellation, and resume through `GET /artifacts`, `GET /runs/{run_id}`, `POST /runs/{run_id}/cancel`, and `POST /runs/{run_id}/resume`.

## Observability

`TraceRecorder` writes `trace_report.json` with phase spans, durations, final state, artifact count, event count, and warning count. `DebugBundleBuilder` writes `debug_bundle_manifest.json`, listing report and trace artifacts without copying raw user files.

## Repo Intelligence

`RepoAnalyzer` detects language mix, framework hints, package/config files, likely test commands, hot files, and generated/dependency directories. Repo maps are attached to repository input metadata so planners and validators can reason about codebase boundaries.

## Ingestion Hardening

Part A adds text encoding detection, symlink warnings, archive entry and uncompressed-size limits, and repository mapping. Archive contents are still inventoried without unpacking unless a future sandbox extraction path is explicitly enabled.

`universal_orchestrator.evals` defines built-in world-readiness cases for report packages, repo implementation traces, and unsafe archive handling. Gates parse typed schemas, validate graph semantics, reconcile task IDs across routing, verify structured worker fields, and recompute checksums. Mutation tests prove malformed artifacts fail. The CLI exposes execution through `python -m universal_orchestrator evals --run`.
