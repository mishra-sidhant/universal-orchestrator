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
- `ai_team.evals`

`ai_team.status` now includes the runtime snapshot, and `ai_team.cancel` writes a durable cancellation request unless the run is already terminal.

## Ingestion Plane

The ingestion plane inventories everything the user supplies, but does not assume every input should enter model context. It fingerprints files, extracts summaries where safe, detects type, scans for secrets and instruction-like untrusted content, and emits a `ContextManifest`.

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

Part A adds deterministic chunking, provenance records, deduplication, and per-task context pack artifacts:

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

## Orchestrator Kernel

The kernel uses `PlannerEnsemble` to create a typed `TaskDAG`. The first planner is deterministic but keeps the ensemble roles visible through tasks for strategy, decomposition, risk review, routing, execution, aggregation, gap analysis, final synthesis, quality, and packaging.

Each run now writes `plan_review.json`, containing deterministic candidate plans from strategic, decomposition, risk, cost, and skeptic planner roles. This is still not a live multi-model ensemble, but it enforces the report's candidate-plan, scoring, merge, and residual-risk contract.

Plan review now also includes critical path analysis, cost-tier estimation, parallel batch simulation, max parallelism, and residual risk summaries.

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

`DeterministicExecutor` dispatches through provider adapters and records structured worker outputs. Each task result includes a worker output object with summary, findings, evidence references, file references, metrics, risks, and next actions. External adapters remain dry-run safe unless network access and provider configuration are explicitly enabled.

`DAGScheduler` now executes tasks by dependency-ready batches, records schedule metadata, uses cache keys for node-level reuse, and writes `schedule_report.json`. This is still single-process deterministic execution, but the scheduler boundary is ready for parallel workers, retries, cancellation, and partial reruns.

Task cache keys now include the context fingerprint, which prevents stale task reuse when the prompt or supplied inputs change.

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

Part B adds `EvidenceAuditor`, which writes `evidence_audit.json` and adjusts citation-support scoring after the final package is assembled. It verifies source inventory, provenance records, worker evidence refs, and an explicit context section in final markdown. Future quality work should add live code test execution and richer citation formatting.

## Artifact Plane

`ArtifactStore` writes one run directory per run under `.uo/runs/{run_id}`. A final product owner assembles the user-facing package, rejects thin fragments, and writes `product_package.json` plus `final_report.md`. When requested, artifact builders create and validate PDF/DOCX outputs.

Each package includes:

- `context_manifest.json`
- `context_cards.json`
- `context_index.json`
- `product_contract.json`
- `task_dag.json`
- `plan_review.json`
- `budget_report.json`
- `delta_execution_plan.json`
- `routing_decisions.json`
- `routing_telemetry.json`
- `execution_results.json`
- `schedule_report.json`
- `validation_findings.json`
- `evidence_audit.json`
- `product_package.json`
- `quality_report.json`
- `trace_report.json`
- `debug_bundle_manifest.json`
- `final_report.md`
- `run_manifest.json`

When requested, packages can also include:

- `final_report.pdf`
- `pdf_validation.json`
- `final_report.docx`
- `docx_validation.json`

When repair is triggered, packages also include:

- `repair_task_dag.json`
- `repair_execution_results.json`

## Runtime And Evaluation

`RuntimeStore` writes SQLite event and run-summary records under the artifact root. This is the first durable-state layer for resumability, audit, cancellation, and dashboard support.

Part A extends runtime durability with state transitions, task records, and resumable snapshots. Each run persists task status, attempt count, cache key, and lifecycle state transitions.

Part B adds durable cancellation requests, terminal-state-aware cancellation rejection, and status snapshots that include task and cancellation metadata.

## Observability

`TraceRecorder` writes `trace_report.json` with phase spans, durations, final state, artifact count, event count, and warning count. `DebugBundleBuilder` writes `debug_bundle_manifest.json`, listing report and trace artifacts without copying raw user files.

## Repo Intelligence

`RepoAnalyzer` detects language mix, framework hints, package/config files, likely test commands, hot files, and generated/dependency directories. Repo maps are attached to repository input metadata so planners and validators can reason about codebase boundaries.

## Ingestion Hardening

Part A adds text encoding detection, symlink warnings, archive entry and uncompressed-size limits, and repository mapping. Archive contents are still inventoried without unpacking unless a future sandbox extraction path is explicitly enabled.

`universal_orchestrator.evals` defines built-in world-readiness cases for report packages, repo implementation traces, and unsafe archive handling. The CLI exposes these through `python -m universal_orchestrator evals`.
