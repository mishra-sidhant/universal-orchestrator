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
- Folder and repository scans with dependency/build/cache ignores. Repositories read redacted hot files plus prompt-matched files under bounded count/byte budgets.
- DOCX paragraph/table extraction through `python-docx` when available.
- PPTX slide and notes extraction through `python-pptx` when available.
- CSV/TSV and XLSX sampling through the standard library and `openpyxl` when available.
- Image metadata extraction through Pillow when available.
- Full-member ZIP/TAR safety scans without unpacking, including traversal and tar link warnings.
- URL/API inventory without network fetch by default; permission-gated fetch enforces scheme, credentials, DNS, public-address, exact-host override, and no-redirect policy.
- Binary metadata records for remaining media and unknown formats.

Planned:

- OCR, archive sandbox extraction, API schema inference, and audio/video transcription.

## Context Intelligence Plane

Context intelligence converts `InputRecord` values into `ContextCard` objects, ranks them against the prompt, and creates `ContextPack` values for task-specific execution.

Current ranking is deterministic lexical overlap plus specificity and risk boosts. The system also writes a context index, conflict markers, and cache metadata for reuse and auditability. Future ranking should add embeddings, recency, trust, freshness, authority, and deeper semantic deduplication.

Context chunk IDs are stable across equivalent runs, carry source/line/page/slide/sheet locators, and are ranked into per-task packs with Unicode-aware word matching. Repository chunks retain file-path and line locators. Provenance records bind those chunks back to source names and URIs:

- `context_chunks.json`
- `context_provenance.json`
- `context_packs.json`

Chunks containing `prompt_injection_risk` text are persisted for audit but excluded from task-consumed evidence refs. The exclusion is chunk-local, so a safe passage in the same PDF or repository remains eligible. Risk cards carry finding provenance but never claim ownership of the source document's chunks.

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

Egress safety is enforced in layers. Context compilation omits chunks with `prompt_injection_risk`; prompt rendering repeats quarantine for manually constructed or stale packs, wraps retained context in untrusted-data delimiters, and supplies an authority preamble. Finally, the HTTP boundary recursively redacts every JSON payload immediately before serialization. Hosted execution policy is rechecked after routing, so keys and even a forged hosted decision cannot bypass `local_only`.

## Orchestrator Kernel

The kernel uses `PlannerEnsemble` to create a five-node typed `TaskDAG`: context aggregation, gap analysis, synthesis, static artifact construction, and quality evaluation. Synthesis is model-backed only when configuration, policy, and budget permit it; otherwise it is extractive. Every node maps to a concrete function in `StageWorkerRegistry`.

Each run writes `plan_review.json` with strategic, decomposition, risk, cost, and skeptic views. Their scores derive from contract artifact coverage, registered-worker coverage, dependency coverage, quality-stage coverage, cache safety, and actual cost tiers; no role has a hardcoded score.

Plan review includes critical path analysis, cost-tier estimation, batch simulation, and residual risks. The current real DAG is linear and truthfully reports max parallelism of one.

The DAG is validated for missing dependencies and cycles before routing.

Part B adds `BudgetController` and `DeltaPlanner`:

- `budget_report.json` records per-task token estimates, effective cost caps, estimated spend, and a per-run estimated usage ledger reconciled to task totals.
- `delta_execution_plan.json` compares the run against the previous successful run and marks tasks reusable only when inputs are unchanged and the scheduler cache entry exists.

Live spend has a separate accounting plane. `CostLedger` reserves the configured estimate under a lock before transport; a call that does not fit the remaining ceiling is never sent and records `budget_stop`. Successful calls commit provider-reported input/output tokens at rates loaded from `provider_rates.json`. `cost_ledger.json` is the per-call authority; `budget_report.json` reconciles estimate and actual, and large estimator drift is warning-level calibration evidence. The default ceiling is $0.50 even when the token budget profile is `unlimited`.

## Routing Plane

`CapabilityRegistry` describes providers by capability, cost tier, health, context limits, and kind. `AdaptiveRouter` selects the best available provider or marks a task as degraded, reshaped, or paused.

Capability values are configured priors for routing. They are not measured provider-quality claims; a prior becomes measured evidence only through a versioned benchmark record.

Current providers:

- `deterministic.tools`: always available local tools.
- `openai.configured`: enabled only when `OPENAI_API_KEY` exists.
- `anthropic.configured`: enabled only when `ANTHROPIC_API_KEY` exists.
- `ollama.local`: enabled only when `OLLAMA_BASE_URL` exists.

Ordinary orchestration remains local/extractive at this phase. A separate, explicit `smoke` command is the only enabled live round trip; it is key-gated, bounded, and excluded from CI.

Part B adds `routing_telemetry.json`, which records every provider considered for every task, including health status, capability score, cost score, total score, eligibility, and rejection reasons.

Configured, policy-eligible providers receive a bounded models-list or equivalent liveness probe before model-capability planning. Results are cached by TTL and persisted in `provider_health_report.json`; measured healthy/degraded/unavailable status replaces configured health priors for routing. `local_only` suppresses hosted probes as well as model calls. A failed family is excluded so another healthy family can route; when all model families are down, the plan remains local/extractive and the final report carries the degraded-mode notice. A true `PAUSE` names the missing capability and tells the operator to configure or restore a matching provider.

## Execution Plane

`StageWorkerRegistry` dispatches DAG nodes to typed stage implementations. Missing handlers return `SKIPPED`; the generic local adapter never manufactures completion. When a complete model configuration and execution policy permit it, `T-SYNTHESIS` routes by capability, cost tier, and health to OpenAI, Anthropic, or Ollama. The bounded context pack enters a strict JSON request contract. Output is schema-validated before use, receives at most one separately metered reformat request, and then either becomes a labeled model result or degrades to the existing extractive worker with a warning. Keyless execution stays extractive.

OpenAI, Anthropic, and Ollama share an injectable HTTP transport. The real transport owns socket deadlines, while fixture transports make success, 429, 5xx, timeout, authentication, fatal, and malformed-response behavior testable without sockets. Provider-level retry is bounded, exponential with jitter, honors `Retry-After`, and applies only to rate-limit, transient, and timeout failures. Live responses normalize provider-reported token usage.

`DAGScheduler` executes real stage tasks by dependency-ready batches, records every attempt, enforces retry and timeout policies, skips dependents after failure, honors durable cancellation, uses versioned cache entries, and writes `schedule_report.json`. It reports cached and executed results through the same observer path. Side-effecting artifact/quality nodes are non-cacheable; artifact build has two attempts for transient local I/O failure. Timed work receives a cooperative completion guard, and scheduler-owned cache, record, and observer commits are fenced after timeout.

Provider I/O uses the containment decision in ADR-002: a hard socket deadline plus the scheduler completion lease. Provider cost reservations register timeout cleanup, and actual usage commits atomically only while the lease is active. A transport that ignores its deadline can finish its thread later, but cannot retain reservation, issue a repair request, commit usage, cache output, or reach delivery state as successful work.

Task cache keys include context, contract, execution policy, provider descriptors, and routing decisions. `ExactMatchCache` deliberately names its behavior: it does not claim semantic similarity. Malformed entries are quarantined, and cached results are treated as successful product fragments. Delta planning compares against the most relevant prior successful run by input-hash similarity and asks the scheduler's validated cache API for reuse availability instead of probing cache files independently.

Run/card/contract identifiers combine UTC time with random entropy. JSON artifacts and exact-cache entries write to a same-directory temporary file, flush, and atomically replace the destination. Generic provider-backed execution records measured start/completion timestamps.

`RepoValidationRunner` writes `repo_validation_report.json`. It executes only Python unittest commands when `allow_shell` is true. Package-manager and Cargo scripts are not auto-detected because they execute repository-controlled code. Child environments are reduced to `PATH`, `HOME`, `LANG`, and command-declared variables.

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

`EvidenceAuditor` writes `evidence_audit.json`. Source-derived workers explicitly declare `evidence_required=true`; runtime measurements declare false and carry no refs. A source claim resolves only when every cited chunk exists and was consumed by that task. Empty source packs remain unsupported, valid-but-unconsumed refs fail audit, and final Sources include only refs from resolved source claims. `citation_support` measures this required-claim coverage; it does not claim semantic entailment or factuality. All score formulas are documented in `docs/quality-metrics.md`.

Evidence is audited before repair so unsupported claims can trigger repair. After the product is assembled, the persisted audit reruns against the actual final markdown; its `final_citations` finding therefore describes the delivered package rather than a pre-assembly snapshot.

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

`RuntimeStore` writes SQLite event and run-summary records under the artifact root. Every connection uses WAL mode and a 5,000 ms busy timeout so independent run/status/cancel requests can safely share the store.

Part A extends runtime durability with state transitions, task records, and resumable snapshots. Each run persists task status, attempt count, cache key, and lifecycle state transitions.

Runtime durability includes state transitions, attempt and failure records, cancellation requests, terminal-state-aware cancellation rejection, status snapshots, and same-run resume from the persisted `run_request.json`.

The stdio adapter parses each line independently, returns JSON-RPC parse errors without terminating, executes notifications without responding, and dispatches `ai_team.run` to a bounded worker pool. This leaves the input loop free to accept `ai_team.cancel` during the active request. FastAPI creates an orchestrator per run or resume request.

The optional FastAPI daemon exposes artifacts, status, cancellation, and resume through `GET /artifacts`, `GET /runs/{run_id}`, `POST /runs/{run_id}/cancel`, and `POST /runs/{run_id}/resume`.

## Observability

`TraceRecorder` writes `trace_report.json` with phase spans, durations, final state, artifact count, event count, and warning count. `DebugBundleBuilder` writes `debug_bundle_manifest.json`, listing report and trace artifacts without copying raw user files.

## Repo Intelligence

`RepoAnalyzer` detects language mix, framework hints, package/config files, likely test commands, hot files, and generated/dependency directories. Repo maps are attached to repository input metadata so planners and validators can reason about codebase boundaries.

## Ingestion Hardening

Part A adds text encoding detection, symlink warnings, archive entry and uncompressed-size limits, and repository mapping. Archive contents are still inventoried without unpacking unless a future sandbox extraction path is explicitly enabled.

`universal_orchestrator.evals` defines built-in world-readiness cases for report packages, repo implementation traces, and unsafe archive handling. Gates parse typed schemas, validate graph semantics, reconcile task IDs across routing, verify structured worker fields, and recompute checksums. Mutation tests prove malformed artifacts fail. The CLI exposes execution through `python -m universal_orchestrator evals --run`.
