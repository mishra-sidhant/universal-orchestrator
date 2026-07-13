# Implementation Log

## Tranche J.2-L.3: Complete Rich Media And Strict Typing Boundaries

Failing-first landmarks:

```text
TypeError: InputIngestor.__init__() got an unexpected keyword argument 'ocr'
TypeError: InputIngestor.__init__() got an unexpected keyword argument 'transcriber'
```

Connected the fixtureable Tesseract and local Whisper command adapters to the ingestion pipeline. Image OCR and timestamped transcripts now pass through the same scan/redact boundary as text sources, retain tool availability and segment metadata, and remain explicitly partial when optional local tools are absent. Removed unnecessary mypy error-code suppression after the full strict source check passed.

Verification:

```text
Ran 193 tests in 5.039s - OK
Ruff: All checks passed
Success: no issues found in 64 source files
```

Final continuation gate:

```text
Ran 198 tests in 4.877s - OK
world_readiness_core: passed
Ruff: All checks passed
Success: no issues found in 64 source files
Successfully built universal_orchestrator-0.1.0.tar.gz and universal_orchestrator-0.1.0-py3-none-any.whl
```

The exact canonical `uv run` commands were rerun after this record: tests, evals, doctor, strict mypy, and isolated build all passed with no credentials or live provider calls.

## Tranche G.7: Complete Provider Health Matrix

Failing-first landmark:

```text
ValueError: No liveness endpoint configured for gemini.configured
ValueError: No liveness endpoint configured for xai.configured
ValueError: No liveness endpoint configured for openai-compatible.local
```

Added redaction-safe models-list probes for Gemini, xAI, and OpenAI-compatible gateways. Subscription CLIs remain execution-status driven because they expose no standard HTTP liveness surface; their quota observations stay explicitly unknown or observed. Hosted health failures now feed the same degraded routing path across the provider matrix.

## Tranche K.2: Persist And Validate Product Plans

## Tranche G.9: Honest Subscription Cost Classification

Failing-first landmark:

```text
AttributeError: 'ProviderCallLedgerEntry' object has no attribute 'billing_mode'
```

Provider ledger rows now carry billing mode and cost status. Subscription CLI usage is counted separately as `allocated_cost_unknown`, while local zero-cost execution is labeled explicitly; metered API totals remain the only values treated as priced USD.

Failing-first landmarks:

```text
AttributeError: 'PlannerEnsemble' object has no attribute 'validate_product_plan'
AssertionError: product_plan.json does not exist
```

Persisted the typed product plan beside the executable DAG and added validation that chapter task references match the run's known task IDs. The validator is strict about run identity and duplicate chapter IDs and emits an auditable empty-errors report for a valid plan.

Verification:

```text
Ran 194 tests in 4.644s - OK
world_readiness_core: passed
```

## Tranche G.5-L.3: Reset-Aware Capacity And Complete Host Controls

Failing-first landmarks:

```text
AssertionError: expired exhausted capacity remained ineligible
AssertionError: MCP cost ceiling was normalized back to the $0.50 default
```

Capacity observations now honor provider reset timestamps: an expired exhausted window becomes unknown and penalized until a fresh response, rather than blocking a connector forever or pretending it is unlimited. The MCP run tools now preserve the full policy, budget, artifact, and URL controls exposed by the core invocation model.

Verification:

```text
Ran 9 capacity tests - OK
Ran 8 MCP tests - OK
Ruff: All checks passed
Success: no issues found in 64 source files
```

## Tranche G.0-G.1: Capacity Foundation And Provider Matrix

Failing-first landmark:

```text
ModuleNotFoundError: No module named 'universal_orchestrator.capacity'
```

Implemented typed capacity states/windows, thread-safe exact reservations, SQLite snapshot persistence, response-header normalization, capacity-aware routing fields, and fixture-tested Gemini and OpenAI-compatible adapters for xAI/local gateways. Capability values remain explicitly configured priors.

Verification:

```text
Ran 166 tests in 3.874s - OK
Success: no issues found in 57 source files
world_readiness_core: passed
```

## Tranche L.1: Headless Host Gateway

Failing-first landmark:

```text
AssertionError: 'ai_team.run_start' not found in MCP tool definitions
```

Added immediate asynchronous MCP run start, durable polling, capacity/events access, and read-only integration configuration for Codex, Claude Code, VS Code/Copilot, and generic MCP hosts. No dashboard or host credential copying was introduced.

Verification:

```text
Ran 190 tests - OK
Success: no issues found in 64 source files
```

## Final Canonical Verification

Executed through the project uv environment after declaring `build` in the dev extra:

```text
Ran 191 tests in 4.420s - OK
world_readiness_core: passed
Success: no issues found in 64 source files
Successfully built universal_orchestrator-0.1.0.tar.gz and universal_orchestrator-0.1.0-py3-none-any.whl
```

Post-release limits regression: observed zero remaining tokens on a fixture response, then verified the next adapter call raised `capacity_exhausted` before the fake transport received any request.

## Tranche J.1-K.1: Safe Media And Rich Artifact Boundaries

Failing-first landmark:

```text
ModuleNotFoundError: No module named 'universal_orchestrator.providers.cli'
```

Added safe archive extraction, optional Tesseract OCR and local Whisper segment parsing, typed product/chapter/slide plans, PPTX construction, and structural slide validation. Archive and media boundaries remain injectable and offline-testable.

Verification:

```text
Ran 188 tests in 4.781s - OK
world_readiness_core: passed
```

## Tranche H.1-I.2: Durable Parallel Handoff And Context Intelligence

Failing-first landmarks:

```text
TypeError: DAGScheduler.__init__() got an unexpected keyword argument 'max_parallel_tasks'
AttributeError: 'RuntimeStore' object has no attribute 'acquire_task_lease'
```

Added bounded dependency-ready parallel execution, SQLite leases and epoch fencing, validated task checkpoints, crash-recovery primitives, provider handoff records, cross-provider synthesis retry, deterministic hybrid retrieval, persisted local embedding vectors, and a structural claim verifier that never calls lexical similarity entailment.

Verification:

```text
Ran 181 tests in 4.729s - OK
Success: no issues found in 62 source files
world_readiness_core: passed
```

## Tranche G.2: Official Subscription CLI Adapters

Failing-first landmark:

```text
ModuleNotFoundError: No module named 'universal_orchestrator.providers.cli'
```

Added injectable subprocess transport, Claude Code JSON execution, Codex JSONL execution, bounded command environments, CLI-owned authentication policy, usage capture, and typed `capacity_exhausted` failures. Added `ai-team capacity` and CLI smoke support. No API key is forwarded into CLI subprocess environments.

Verification:

```text
Ran 170 tests in 3.922s - OK
Success: no issues found in 59 source files
world_readiness_core: passed
```

The standard `uv` and isolated build commands were unavailable in this shell: `uv` is not installed and the isolated build environment cannot download `hatchling` without network access. The bundled Python verification passed; the operator must rerun the canonical `uv` gate before merging.

Date: July 8, 2026

## Source Understanding

- Read the 21-page Universal AI Executive Kernel architecture report from `/Users/sidhantmishra/Downloads/Universal_AI_Executive_Kernel_Report.pdf`.
- Rendered the report into PNG pages under `tmp/pdfs/` for visual inspection.
- Confirmed the report's core planes: host/adapters, ingestion/context intelligence, adaptive orchestration, quality/repair, product delivery, and artifact store.

## Repository Baseline

- Workspace started as an empty Git repository on `main` with no commits.
- Built a Python-first product scaffold from scratch.

## Landmarks Completed

- Added product requirements, implementation plan, architecture, configuration, testing, and implementation log documentation.
- Added Pydantic v2 data models for all major kernel objects.
- Added deterministic ingestion for prompts, files, folders/repos, PDFs, URLs, and binary metadata.
- Added security scanning and redaction for context summaries.
- Added context card creation, ranking, and context packs.
- Added product contract compiler and definition-of-done gates.
- Added planner ensemble v1 and typed DAG validation.
- Added provider registry and adaptive router.
- Added deterministic executor.
- Added quality gate engine.
- Added artifact store and run manifest generation.
- Added standard-library CLI.
- Added optional FastAPI daemon surface.
- Added unit tests.

## Seven-Milestone Expansion

Completed after the initial MVP baseline:

1. Baseline commit: validated and committed `8ecda2d`.
2. Provider execution layer: added deterministic, OpenAI Responses, Anthropic Messages, and Ollama adapters with dry-run-safe execution.
3. Credential/config flow: added `.env.example`, `.env.local` convention, `configure`, and richer provider readiness checks in `doctor`.
4. Structured task outputs: each execution result now includes findings, evidence refs, files, metrics, risks, and next actions.
5. Targeted repair loop: quality failures create a repair DAG, route repair tasks, execute them, write repair artifacts, and re-run quality.
6. Richer ingestion: added DOCX, PPTX, CSV/TSV/XLSX, image metadata, safe ZIP/TAR inventory, and permission-gated URL/API fetch.
7. Host adapter surface: added a stdio JSON-RPC/MCP-style adapter exposing `ai_team.run`, `status`, `artifacts`, `providers`, `doctor`, `configure`, and `cancel`.

## Verification Commands Run

```bash
PYTHONPATH=src /Users/sidhantmishra/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests
PYTHONPATH=src /Users/sidhantmishra/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m universal_orchestrator doctor
PYTHONPATH=src /Users/sidhantmishra/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m universal_orchestrator providers
PYTHONPATH=src /Users/sidhantmishra/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m universal_orchestrator run "Use the architecture report and this repo to produce the first implementation package for the Universal AI Executive Kernel" /Users/sidhantmishra/Downloads/Universal_AI_Executive_Kernel_Report.pdf .
```

Latest observed test result:

```text
Ran 20 tests
OK
```

Latest self-run package:

```text
.uo/runs/run_20260708173959962906
```

Quality result:

- Passed: true.
- Artifact integrity: pass.
- Degraded deterministic routing was explicitly reported for strategic/synthesis tasks because hosted providers are not configured.

## Non-Provider World-Readiness Hardening

Completed after live provider execution was explicitly deferred:

- Added deterministic planner candidate review and `plan_review.json` artifacts.
- Added context index, conflict markers, and exact-match cache metadata.
- Added a final product owner that assembles final packages and rejects weak fragments.
- Added PDF and DOCX artifact builders with deterministic validation.
- Added structured validator registry and `validation_findings.json`.
- Added security policy helpers for workspace paths, archive members, URL permission, and authority checks.
- Added SQLite runtime event and run-summary store under the artifact root.
- Added built-in world-readiness eval cases and CLI/MCP exposure.

Latest non-provider hardening validation:

```text
Ran 27 tests
OK
```

Latest PDF artifact validation run:

```text
.uo/runs/run_20260709020729937439
```

PDF render check:

- Generated `final_report.pdf`.
- Rendered two PNG pages with Poppler under `tmp/pdfs/world-ready-final-*.png`.
- Inspected both rendered pages for legibility, clipping, and layout issues.
- `pdf_validation.json` reported no errors.

## Part A Remaining-Gap Implementation

Part A addressed the first six remaining non-provider gaps:

1. Real DAG scheduler foundations: dependency-ready batches, schedule records, cache keys, and `schedule_report.json`.
2. Durable run lifecycle: SQLite state transitions, task records, resumable snapshots, and persisted attempts/cache keys.
3. Planner ensemble depth: critical path, cost-tier estimation, parallel batch simulation, and richer `plan_review.json`.
4. Context intelligence maturity: chunking, provenance, deduplication, per-task context packs, and budget-aware pack compilation.
5. Repo intelligence: framework detection, language counts, package files, hot files, dependency/generated dirs, and test command detection.
6. Ingestion hardening: encoding detection, symlink warnings, archive entry/uncompressed-size limits, and repo maps.

Latest Part A validation:

```text
Ran 35 tests
OK
```

Latest Part A validation run:

```text
.uo/runs/run_20260709030839873328
```

## Part B Remaining-Gap Implementation

Part B addressed the next six remaining non-provider gaps:

1. Budget control: per-task token/cost estimates, effective cost caps, and `budget_report.json`.
2. Provider health and routing telemetry: provider scorecards, rejection reasons, and `routing_telemetry.json`.
3. Delta execution planning: previous-run comparison, context-fingerprinted task cache keys, and `delta_execution_plan.json`.
4. Durable cancellation/status: runtime cancellation table, terminal-aware cancellation rejection, CLI `cancel`, and MCP `ai_team.cancel`.
5. Observability/debuggability: phase traces, durations, debug bundle manifest, `trace_report.json`, and `debug_bundle_manifest.json`.
6. Evidence/citation audit: final-package evidence audit, worker evidence checks, provenance checks, and citation-support quality adjustment.

Latest Part B validation:

```text
Ran 45 tests
OK
```

Latest Part B validation run:

```text
.uo/runs/run_20260709041910441024
```

## Part C Remaining-Gap Implementation

Part C addressed the next six remaining non-provider gaps:

1. Approval and risk gates: internet, repo-write, shell, and cloud-provider approval checks with `approval_report.json`.
2. Safe local repo validation: allowlisted no-shell command execution, skipped validation plans, and `repo_validation_report.json`.
3. Patch and package artifacts: deterministic patch-plan generation, ZIP delivery bundles, and validation artifacts.
4. Artifact integrity audit: recomputed hashes/sizes, expected-file checks, duplicate detection, and `artifact_integrity_report.json`.
5. Daemon parity: status, artifacts, and terminal-aware cancellation helper/endpoints matching CLI/MCP behavior.
6. Executable eval runner: built-in world-readiness cases can now run and write `eval_report.json`.

Latest Part C validation:

```text
Ran 58 tests
OK
```

Latest Part C validation run:

```text
.uo/runs/run_20260709132754310701
```

Latest Part C eval report:

```text
.uo/evals/part_c/eval_report.json
```

## Tranche D Trustworthy Runtime And Delivery

Completed July 10, 2026 after a fresh report-to-code validation:

1. Enforced privacy and egress policy: added an effective execution policy, separated internet fetch from cloud permission, filtered hosted providers during routing, and rechecked policy immediately before adapter execution. `local_only` cannot be bypassed by flags or credentials.
2. Completed lifecycle behavior: failures persist `failure.json` and SQLite failure records; cancellation is terminal before delivery; the scheduler records retries, timeouts, dependency skips, and attempts; failed or cancelled runs resume from `run_request.json` under the same run ID.
3. Corrected cache and delta semantics: valid cache hits count as successful outputs, cache records are schema/version checked, malformed entries are quarantined, cache fingerprints include contract/policy/provider/routing context, and delta planning chooses the most similar prior successful run.
4. Rebuilt artifact finalization: repository analysis emits an honest `patch_plan.md`; payloads are audited before a one-time manifest write; `checksums.json` covers payloads plus the manifest; the ZIP includes manifest/checksums/trace/debug/integrity; `delivery_receipt.json` binds ZIP, manifest, checksums, and validation hashes.
5. Added context/evidence scaffolding: ingestion retains redacted extracted text, stable chunks preserve source locators and tail content, and the final report can render chunk references. Tranche E later established that workers had not demonstrably consumed those references; the earlier "claim-level evidence" wording is superseded.
6. Added derived quality/eval scaffolding. Tranche E later established that `factuality` and `style_quality` were misnamed synthetic proxies; the trustworthy metrics replacement is tracked in the July 10 review disposition.
7. Hardened distribution: parser and artifact-builder dependencies are declared in the default package, CI covers Python 3.11-3.13, and build validation produces both sdist and wheel.

Validation completed:

```text
73 unittest tests passed
Ruff: all checks passed
Built-in eval suite: 3/3 cases passed
Package build: universal_orchestrator-0.1.0.tar.gz and universal_orchestrator-0.1.0-py3-none-any.whl
git diff --check: clean
```

Strict `mypy src` was also run and exposed a pre-existing backlog in optional provider, ingestion, daemon, and MCP boundary typing. It is documented rather than hidden and is not yet a CI gate.

Provider keys remain intentionally absent. Add them later to repository-root `.env.local` using `.env.example`; hosted runs also require `--allow-internet --allow-cloud`. OpenAI needs `OPENAI_API_KEY` and `OPENAI_MODEL`; Anthropic needs `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL`; Ollama needs `OLLAMA_BASE_URL` and `OLLAMA_MODEL`.

## Tranche E.0 Stop The Bleeding

Accepted the July 10 adversarial review in full and added regression tests before implementation.

Failing-first transcript against `3e74812`:

```text
test_post_repair_quality_rates_use_original_and_repair_task_union:
ValidationError: continuity <= 100, input_value=118

test_pipeline_repair_uses_scheduler_audits_before_repair_and_assembles_once:
ValidationError: continuity <= 100, input_value=118

test_failed_execution_finding_uses_failure_description:
AssertionError: 'No execution result failed.' was emitted for a failed task

test_secret_in_prompt_never_reaches_files_or_delivery_zip:
secret found in run_request.json

test_quality_failed_run_needs_attention_without_delivery_receipt:
repair path crashed before an honest terminal state could be produced
```

Implemented corrections:

- Quality rates use the union of planned and executed task IDs, preventing repair tasks from inflating scores beyond 100.
- Every validation finding carries distinct pass and fail messages; violations use the fail description.
- Evidence auditing occurs before repair, repair executes through `DAGScheduler`, attempt records are persisted, and the final product is assembled once.
- Prompt secrets are redacted in `run_request.json`, `context_manifest.json`, embedded run-manifest invocation, and therefore the ZIP.
- Added terminal `needs_attention`; unresolved quality runs still receive a diagnostics bundle but never a delivery receipt.

E.0 verification:

```text
78 unittest tests passed
3/3 built-in eval cases passed
doctor passed
Ruff clean after removing one unused test import
```

## Tranche E.1 Evidence Honesty

Failing-first transcript against `fcbb77b`:

```text
test_empty_task_pack_does_not_fallback_to_global_chunks:
expected [], got ['chunk_global']

test_executor_passes_consumed_task_refs_to_adapter_and_output:
adapter consumed [], expected ['chunk_consumed']

test_auditor_rejects_real_but_unconsumed_chunk_reference:
EvidenceAuditor did not accept a consumed-ref map

test_missing_refs_identifies_exact_unsupported_task:
EvidenceAuditor did not accept a consumed-ref map

test_quality_score_schema_has_no_synthetic_check_names:
'factuality' remained in QualityScore
```

Implemented corrections:

- Removed the global source fallback. Refs are selected only from each task's delivered pack; external source chunks are preferred over prompt chunks within that same pack.
- `DeterministicExecutor` creates per-task context with `consumed_chunk_refs`; adapters and structured worker output receive the same list.
- Evidence audit rejects nonexistent refs and real-but-unconsumed refs, identifies the exact unsupported tasks, and computes citation coverage only from resolved claims.
- Final report citations and Sources are rendered only from resolved evidence claims.
- Removed synthetic `factuality` and `style_quality`; renamed parser, routing, and artifact-presence proxies honestly. Added `docs/quality-metrics.md` with every formula and limitation.

Existing-test dispositions: `test_workers` now supplies `consumed_chunk_refs` instead of the superseded `input_refs` fallback. Quality fixture constructors use the renamed schema. No threshold or failure assertion was weakened.

## Tranche E.2 One Kernel

Failing-first transcript against `05790dd`:

```text
test_execution_plan_contains_only_real_stage_nodes:
expected five stage IDs; got static T-001 through T-011

test_plan_candidate_scores_change_with_real_contract_coverage:
0.88 was unchanged when artifact coverage was removed

test_deterministic_adapter_never_echo_completes_unimplemented_work:
expected SKIPPED; got COMPLETED

test_unavailable_strategic_capability_reaches_reshape_or_pause:
expected RESHAPE/PAUSE; got ROUTE_DEGRADED

test_default_local_run_contains_real_stage_outputs_and_no_echo_lines:
eleven "completed by local deterministic tools" lines found
```

Implemented corrections:

- Added `StageWorkerRegistry` with real aggregation, gap, extractive synthesis, static artifact, and quality handlers.
- Reduced the execution plan to those five registered workers and derived plan scores from observable contract/DAG properties.
- Removed fictional deterministic reasoning/research/style capabilities; routing now requires all capability thresholds.
- Generic deterministic adapter calls skip explicitly. Default local reports contain measured/extractive summaries and zero echo-completion lines.
- Pure stages are cacheable; side-effecting artifact/quality stages rerun. Scheduler observers receive cached and executed results.
- Added ADR-001 with alternatives, consequences, pre/post-DAG boundaries, and residual coupling.

Existing-test dispositions: budget tests now assert the real all-free plan; repair tests assert unsupported repair work reshapes instead of fake completion; deterministic capability tests assert only registered stage capabilities; cache tests expect three pure hits; old task-ID assertions use the five stage IDs; E.0 failure injection now fails the real first handler before quality runs.

## Tranche E.3 Security Floor

Failing-first transcript against `18670f9`:

```text
9 test methods produced 15 failures and 2 errors:
- JSON/dotenv quoted values, GitHub, Google, Slack, JWT, private-key, and credential-URL patterns escaped
- traversal at ZIP entry 61 was absent from unsafe_paths
- tar unsafe_links key was absent
- 127.0.0.1 was allowed and metadata-endpoint ingestion reached the network mock
- npm test and cargo test were auto-detected
- OPENAI_API_KEY, ANTHROPIC_API_KEY, and unrelated parent variables reached subprocess env
- OpenAI _safe_payload returned the secret unchanged
- an injection-flagged source chunk appeared in worker evidence refs
```

Implemented corrections:

- Expanded scan/redaction patterns for every requested secret family, including quoted JSON/dotenv values and multiline private keys.
- Archive inventory samples remain bounded for display, but safety checks inspect every member and flag all tar symbolic/hard links.
- URL policy resolves hosts and blocks unsafe schemes, URL credentials, DNS failures, and non-public address classes. Redirects are disabled; exact-host overrides are exposed through CLI/MCP.
- Removed automatic npm/cargo test detection and allowlisting. Python validation subprocesses receive a minimal environment.
- OpenAI dry-run payload redaction is recursive.
- Injection-flagged source chunks remain auditable but cannot enter consumed evidence refs.
- Deleted policy authority/path/archive helpers that had no runtime caller; real archive behavior is covered at ingestion.

Existing-test disposition: the world-readiness policy test no longer calls deleted test-only path/archive helpers; stronger archive and SSRF tests cover live boundaries.

Validation gate (2026-07-11, bundled project runtime):

```text
unittest: 97 tests passed
ruff: All checks passed
evals: 3/3 passed
doctor: passed
package: universal_orchestrator-0.1.0.tar.gz and universal_orchestrator-0.1.0-py3-none-any.whl built successfully
git diff --check: passed
```

## Tranche E.4 Runtime Correctness

Failing-first transcript against `0aa1437`:

```text
8 test methods: 5 failures, 2 errors, 1 apparent pass
- artifact build retry policy remained max_attempts=1; flaky build ran only once
- SQLite journal mode was delete rather than wal
- scheduler called the unguarded executor path and reported an assertion instead of timeout
- final assembly, artifact build, artifact validation, and packaging states were absent
- PLAN_REVIEW, AGGREGATING, and GAP_ANALYSIS remained dead enum values
- malformed JSON raised JSONDecodeError and terminated stdio processing
- Orchestrator still exposed the stale executor field
The apparent MCP concurrency pass was found to be a swallowed assertion; the test was strengthened before production changes to require sub-500 ms completion and two successful responses.
```

Implemented corrections:

- Removed orchestrator-level executor state and proved two concurrent runs keep source context isolated.
- Enabled SQLite WAL and a 5,000 ms busy timeout on every connection.
- Added a cooperative per-attempt completion guard; timeout deactivates it before terminal recording, and late work cannot enter scheduler cache, attempt, or observer commits.
- Added real repair/final-assembly/artifact-build/artifact-validation/packaging transitions and deleted three unused states. Failure injection proves post-DAG stage attribution.
- Hardened stdio JSON-RPC parsing, notification semantics, and active-run cancellation concurrency.
- Activated two artifact-build attempts and proved a real pipeline recovers from a transient first failure.

Existing-test disposition: no existing test was weakened or deleted. The artifact construction/validation block was separated without changing artifact names or delivery ordering.

Validation gate (2026-07-11, bundled project runtime):

```text
unittest: 107 tests passed
ruff: All checks passed
evals: 3/3 passed
doctor: passed
package: universal_orchestrator-0.1.0.tar.gz and universal_orchestrator-0.1.0-py3-none-any.whl built successfully
dead-state audit: every remaining RunState has a live runtime or terminal use
git diff --check: passed
```

## Tranche E.5 Real Inputs And Provider Plumbing

Failing-first transcript against `be52ac8`:

```text
12 test methods produced 11 failures and 2 errors:
- repo source bodies never appeared in chunks or final citations
- flagship report+repo prompt compiled as repo_implementation
- provider previews omitted the ContextPack and returned no usage estimate
- budget_report.json had no usage ledger
- Anthropic max_tokens remained fixed at 1024
- live HTTP helper had no retry/backoff parameters
- 500 IDs at frozen time collapsed to one value
- JSON writes never invoked atomic replace
- SemanticCache name and dead report/executor renderers remained
- delayed provider execution still reported a near-zero duration
- PDF extraction lost <x> markup and H2 had no dedicated handling
The first Unicode probe accidentally ranked via an English title; it was strengthened before production changes with an all-Devanagari card and a tight-budget competing chunk.
```

Implemented corrections:

- Read and redact repository hot/prompt-matched files under bounded count/byte budgets; chunk locators retain repository path and line range. End-to-end delivery cites an actual source file.
- Made explicit report/research/PDF intent outrank repository presence and made lexical ranking Unicode-aware.
- Added one bounded provider-context renderer for OpenAI, Anthropic, and Ollama previews, explicit estimated usage, configurable Anthropic output tokens, and bounded 429/5xx backoff scaffolding behind live execution.
- Reconciled per-task estimates into a usage ledger inside the existing `budget_report.json`; no JSON artifact type was added.
- Added random ID entropy, atomic JSON/cache replacement, measured provider-backed timestamps, exact cache naming, and scheduler-owned cache validation for delta planning.
- Removed dead artifact/executor renderers and fixed PDF markup escaping plus H2 styling.

Existing-test disposition: four cache imports were renamed without changing their assertions. No existing behavioral test was weakened or deleted.

Validation gate (2026-07-11, bundled project runtime):

```text
unittest: 119 tests passed
ruff: All checks passed
evals: 3/3 passed
doctor: passed
package: universal_orchestrator-0.1.0.tar.gz and universal_orchestrator-0.1.0-py3-none-any.whl built successfully
JSON artifact types added: none
git diff --check: passed
```

## Tranche E.6 Bare-Host And End-To-End Proof

Failing-first and proof-driven transcript against `a1ab9f6`:

```text
bootstrap structure: 2 tests failed (README had no uv flow; CI had no typing job)
Python 3.14 connection regression: 4 ResourceWarnings in the focused RuntimeStore test
source-evidence regression: KeyError evidence_required
mixed-source regression: initial sentinel assertion had a prompt-citation loophole; strengthened non-prompt assertion failed
risk provenance regression: risk records incorrectly owned source chunk IDs
first flagship run: quality_passed=false because runtime-derived claims were treated as uncited source claims
second flagship inspection: quality passed, but the only Source was User prompt
pre-release full gate: secret-in-prompt test caught raw prompt text in context-pack task queries
```

Implemented corrections:

- Added official standalone `uv` bootstrap, `uv.lock`, `uv run` doctor/run/test examples, and a separate visible non-blocking mypy CI job while preserving the blocking 3.11-3.13 matrix.
- Closed every RuntimeStore SQLite connection deterministically; the Python 3.14 suite is warning-free.
- Added `evidence_required`, restricted evidence refs to extractive synthesis, computed citation support only over source-derived claims, and included the redacted prompt in retrieval queries.
- Made injection exclusion chunk-local and prevented risk-card provenance from owning source chunks.
- Kept the secret boundary intact by using the redacted prompt for every persisted task query.

Accepted flagship proof:

```text
run_id: run_20260711021842873947_ec53fef0
run_type: research_report
quality_passed: true
evidence_audit: passed; invalid refs=0; unconsumed refs=0
Sources: real repository and Universal_AI_Executive_Kernel_Report.pdf chunks
echo line count: 0
artifact_integrity_report: passed
delivery receipt state: delivered
delivery ZIP: 31 entries, testzip clean, receipt hash matched
QualityScore fields: artifact_presence, citation_support, code_validation,
  completeness, continuity, parse_confidence, routing_efficiency
```

Typing visibility: `mypy src` reports 79 errors in 19 files and remains explicitly non-blocking. This is a recorded adapter/optional-library typing backlog, not a suppressed gate.

Final verification gate (2026-07-11, uv-provisioned CPython 3.14.6):

```text
uv install: uv 0.11.28 official standalone installer succeeded without system Python
uv sync --all-extras --dev: succeeded; uv.lock generated
unittest: 125 tests passed, ResourceWarning checks enabled, zero warnings
ruff src tests: All checks passed
evals --run: 3/3 passed (report PDF, repo trace, unsafe archive)
doctor: passed; provider credentials correctly reported absent
uv build: universal_orchestrator-0.1.0.tar.gz and universal_orchestrator-0.1.0-py3-none-any.whl
wheel clean-environment smoke: version, doctor, local run, quality pass
sdist clean-environment smoke: build/install, version, doctor, local run, quality pass
mypy src: non-blocking baseline, 79 errors in 19 files
flagship proof: run_20260711021842873947_ec53fef0, accepted
git diff --check: passed
```

## Tranche F.0 Citation Honesty Residuals

Failing-first transcript against `82b2b59`:

```text
3 focused tests: 1 passed, 2 failed
- non-source contract received synthetic citation_support=100 instead of provisional 0
- delivered evidence_audit.json persisted final_citations=false although final_report.md had Sources
- measured audit with one supported and one unsupported evidence-required claim produced 50 (already correct)
```

Implemented corrections:

- Deleted the contract-keyword citation branch. `QualityGateEngine` emits a provisional zero; only `EvidenceAuditor.apply_to_quality` writes the supported/required claim ratio.
- Preserved the pre-repair audit and added a post-assembly audit against the actual `ProductPackage`, so the persisted final-citation finding agrees with delivery.
- Clarified the dead-code ledger wording: removed `DeterministicExecutor._summary` was unrelated to the live `StructuredWorkerOutputBuilder._summary` in `workers.py`.

Validation gate (2026-07-11):

```text
unittest: 128 tests passed
ruff src tests: All checks passed
evals --run: 3/3 passed
doctor: passed with provider credentials absent
package: wheel and source distribution built successfully
git diff --check: passed
```

## Tranche F.1 Bounded Live Transport Substrate

Failing-first transcript against `9260735`:

```text
test_tranche_f1 import failed: handle_smoke did not exist
ProviderError, ProviderErrorKind, FakeTransport, HTTPResponse, and TransportTimeout did not exist
```

Implemented:

- Added an injectable one-request HTTP transport contract, a real `urllib` transport, and a scripted in-memory fake backed by recorded response fixtures.
- Classified provider failures as auth, rate-limit, transient, fatal, timeout, or malformed output. Only rate-limit, transient, and timeout failures retry; attempts are bounded, backoff is exponential with jitter, and numeric `Retry-After` takes precedence.
- Carried every task timeout to the socket call and normalized provider-reported token usage across OpenAI, Anthropic, and Ollama.
- Added the explicit, key-gated `smoke` command. Its fixed tiny prompt reports latency and usage; it does not invent USD cost before F.3 pricing exists.
- Labeled capability scores as configured priors rather than measured quality facts.

Validation gate (2026-07-11, no keys and no live calls):

```text
unittest: 133 tests passed
ruff src tests: All checks passed
evals --run: 3/3 passed
doctor: passed with all provider credentials absent
package: wheel and source distribution built successfully
git diff --check: passed
```

## Tranche F.2 Provider Egress Safety

Failing-first transcript against `80a742c`:

```text
4 focused tests: 1 assertion failure, 3 boundary errors
- hostile chunk remained in the compiled ContextPack
- CapabilityRegistry did not accept injected transports
- Orchestrator did not accept a live-configured fixture registry
- outbound recursive redaction/quarantine could not be exercised through the registry
```

Implemented:

- Quarantined prompt-injection-risk chunks during context compilation and repeated that enforcement while rendering provider context.
- Wrapped retained context in explicit untrusted-data delimiters with an authority preamble.
- Recursively redacted provider payloads at the last process boundary before JSON serialization, including prompt, context, and nested metadata.
- Injected transports through `CapabilityRegistry` and allowed a registry to be injected into `Orchestrator`, enabling full offline live-configuration proofs.
- Proved a forged hosted route cannot bypass `local_only`, even with key, model, network permission, and dry-run disabled.
- Swept every file in a live-configured run and every member of its delivery ZIP for planted key material; zero matches.

Validation gate (2026-07-11, no real keys and no live calls):

```text
unittest: 137 tests passed
ruff src tests: All checks passed
evals --run: 3/3 passed
doctor: passed with all provider credentials absent
package: wheel and source distribution built successfully
key sweep: run artifacts 0 matches; delivery ZIP members 0 matches
local_only with live configuration: 0 transport invocations
git diff --check: passed
```

## Tranche F.3 Truthful Live Cost Accounting

Failing-first transcript against `f053b00`:

```text
test_tranche_f3 import failed: universal_orchestrator.cost_ledger did not exist
RateTable, BudgetStopError, and actual provider-call ledger contracts did not exist
```

Implemented:

- Added a packaged, versioned JSON rate table with provider defaults and exact-model override slots.
- Added a thread-safe per-run cost ledger that reserves estimates before transport and records a structured budget stop when the remaining ceiling is insufficient.
- Normalized actual token usage into per-call rows with task, provider, model, estimated/actual cost, and rate-table provenance.
- Added estimate/actual reconciliation to `budget_report.json`; threshold drift is a quality warning, not a gate failure.
- Added `cost_ledger.json` to every run and its delivery integrity inventory, including zero-spend local runs.
- Kept the default ceiling at $0.50 for runs and smoke calls; the separate `unlimited` token profile does not raise it.

Validation gate (2026-07-11, no real keys and no live calls):

```text
unittest: 142 tests passed
ruff src tests: All checks passed
evals --run: 3/3 passed
doctor: passed with all provider credentials absent
package: wheel and source distribution built successfully
wheel inventory: provider_rates.json, pricing.py, and cost_ledger.py present
pre-call budget stop fixture: 0 transport invocations
actual usage fixture: 11 input + 7 output tokens, $0.000160 actual
git diff --check: passed
```

## Tranche F.4 Validated Model Synthesis

Failing-first transcript against `b54c2a0`:

```text
5 focused tests: 2 assertion failures, 3 missing-contract errors
- no synthesis_path existed
- configured provider was never selected for T-SYNTHESIS
- fabricated model refs could not enter the evidence audit
- tiny ceiling did not budget-stop because no model call was attempted
- keyless extractive output had no explicit production-path label
```

Implemented:

- Made planning select a model-capability synthesis node only when a complete configured provider and effective policy permit it; keyless planning remains extractive.
- Routed model synthesis through the common adapter, transport, timeout, egress, and cost-ledger machinery with a bounded ContextPack and inline chunk IDs.
- Added strict JSON validation for summary, findings, and per-claim evidence refs. One metered reformat request is allowed; repeated invalid output falls back extractively with a degradation warning.
- Audited model claims individually, unioned supported refs for final citations, and made fabricated refs fail evidence quality and terminal delivery.
- Added the explicitly weak lexical-overlap warning floor without claiming entailment.
- Labeled final production path as `model`, `model_repaired`, `extractive_fallback`, or `extractive`.
- Tightened provider readiness so key and model must both exist before routing advertises execution.

Validation gate (2026-07-11, fixtures only, no live calls):

```text
unittest: 149 tests passed
ruff src tests: All checks passed
evals --run: 3/3 passed
doctor: passed with all provider credentials absent
package: wheel and source distribution built successfully
model success: 1 fixture call, grounded claim resolved, path=model
bounded repair: exactly 2 fixture calls; success and extractive fallback both pinned
fabricated ref: audit failed, claim unsupported, needs_attention
budget stop: 0 transport calls, needs_attention, stop in both cost and budget reports
git diff --check: passed
```

## Tranche F.5 Measured Health And Fallback Modes

Failing-first transcript against `d10f3bd`:

```text
test_tranche_f5 import failed: universal_orchestrator.health did not exist
No measured liveness, TTL cache, health artifact, cross-family fallback proof,
degraded-mode notice, actionable capability pause, or Ollama full-path parity existed
```

Implemented:

- Added bounded GET liveness probes for OpenAI, Anthropic, and Ollama with healthy/degraded/unavailable classification and a 60-second cache.
- Refreshed only configured, policy-eligible providers; `local_only` suppresses hosted probes and calls.
- Persisted measured status and routing priors in `provider_health_report.json` and fed measured reliability into routing.
- Proved OpenAI-down routes to Anthropic; all hosted models down retains local extractive synthesis and names the degraded provider in the final report.
- Made `PAUSE` guidance name the unavailable capability and the provider configuration/restoration action.
- Exercised Ollama through the same health, transport, taxonomy, synthesis, and cost-ledger path with a zero-cost row.

Validation gate (2026-07-11, fixtures only, no live calls):

```text
unittest: 154 tests passed
ruff src tests: All checks passed
evals --run: 3/3 passed
doctor: passed with all provider credentials absent
package: wheel and source distribution built successfully
health cache: repeated check produced 1 fixture request
OpenAI down: 1 probe; Anthropic: 1 probe + 1 synthesis call
all hosted down: extractive path with unavailable notice
Ollama: 1 probe + 1 synthesis call, actual_usd=0
git diff --check: passed
```

## Tranche F.6 Late-Completion Containment

Failing-first transcript against `b0e5910`:

```text
hung transport test: scheduler timed out honestly, but cost_ledger.json retained
reserved_usd=0.016890 at run close; no atomic provider-side lease fence existed
```

Implemented:

- Extended the scheduler completion guard with timeout cleanups and atomic active-lease commits.
- Registered provider cost reservations for immediate cleanup when the task lease closes.
- Propagated the completion guard into model calls; responses are checked before validation and before any repair request.
- Fenced actual usage commit under the same lease, so timeout and commit have one ordering authority.
- Added ADR-002 accepting in-process provider I/O with socket deadlines plus the proven scheduler lease, and listed the cases that require stronger isolation.

Validation gate (2026-07-11, fixtures only, no live calls):

```text
unittest: 155 tests passed
ruff src tests: All checks passed
evals --run: 3/3 passed
doctor: passed with all provider credentials absent
package: wheel and source distribution built successfully
hung transport: 1-second task timeout, needs_attention, reserved_usd=0
late valid response: 0 ledger rows, 0 repair calls, no successful late commit
git diff --check: passed
```

## Tranche F.7 Native Versus Orchestrated Benchmark

Failing-first transcript against `528cf46`:

```text
test_tranche_f7 import failed: universal_orchestrator.bench did not exist
No bench command or native/orchestrated comparison artifact contract existed
```

Implemented:

- Added `ai-team bench <prompt> [paths...]` and a reusable `BenchmarkRunner`.
- Built the native arm from one direct call to the strongest healthy configured model with the same ingested source context and an independent cost ceiling/ledger.
- Built the orchestrated arm through the complete pipeline and copied its final output, cost ledger, quality report, and evidence audit into the comparison directory.
- Emitted per-path measured latency and actual fixture-priced cost, with both outputs side by side.
- Set `automated_superiority_claim` to null and stated that only human judgment interprets the measurement.
- Kept real benching operator-only; no agent or CI live call was made.
- Reduced the visible strict typing backlog from 79 errors in 19 files to 71 errors in 17 files while annotating the new live paths.

Final Tranche F verification gate (2026-07-11, fixtures only):

```text
unittest: 157 tests passed
ruff src tests: All checks passed
evals --run: 3/3 passed
doctor: passed with all provider credentials absent
fixture bench: 1 liveness + 1 native + 1 orchestrated fake request
fixture bench cost: native=$0.000450, orchestrated=$0.000450
key sweep: run artifacts 0 matches; delivery ZIP members 0 matches
local_only with live configuration: 0 transport invocations
mypy src: visible non-blocking baseline, 71 errors in 17 files
package: wheel and source distribution built successfully
git diff --check: passed
```

### Operator Live Evidence

Pending operator-provided keys in repository-root `.env.local`. The agent and CI did not execute these commands.

```text
OpenAI smoke: pending operator execution
Anthropic smoke: pending operator execution
Ollama smoke: pending operator execution if configured
Real bench: pending operator execution
```

## Tranche M: Reliability Closure And Product-Quality Execution

Failing-first checkpoints:

```text
capacity regression: provider authorization omitted REQUESTS and TOTAL_TOKENS; expired snapshots had no effective status API
resume regression: a second scheduler invocation re-executed a completed task because latest_checkpoint() was never consumed
handoff regression: synthesis attempted one alternative and escaped on the second provider failure
artifact regression: forced validate_pdf() failure still returned delivered with quality_passed=true
media regression: redaction happened before OCR/transcript scanning, so raw secret findings were lost
chapter regression: ProductPlan contained chapter-1 only and artifact assembly did not depend on chapter outputs
```

Implemented:

- Exact request, directional-token, total-token, concurrency, and durable bounded subscription reservations; stale capacity observations are exposed as `unknown`.
- Fingerprinted checkpoint recovery with distinct checkpoint telemetry and mandatory rerun for side-effecting tasks.
- Bounded multi-hop handoff across at most three attempts and two handoff records, preserving the same task, context pack, and budget boundary.
- Injectable claim verification, contradiction blocking, and raw-before-redaction OCR/transcript security scanning.
- A real three-chapter DAG with independent findings/evidence and risks/actions tasks, plus chapter-aware report and slide assembly.
- Structural and render-aware PDF/DOCX/PPTX validation wired into the final quality result and delivery-receipt gate.

Verification transcript for this implementation:

```text
targeted M.0/M.1 capacity tests: passed
checkpoint and lease tests: passed
multi-hop handoff fixture: passed (provider-a -> provider-b -> provider-c)
claim contradiction and raw OCR security tests: passed
chapter DAG and artifact gate tests: passed
ruff check src tests: passed
full unittest suite: 208 tests passed
evals: pending final committed-tree gate
doctor: pending final committed-tree gate
package build: pending final committed-tree gate
```

Final committed-tree gate (2026-07-12):

```text
unittest: 208 tests passed
evals --run: 3/3 passed
doctor: passed with all provider credentials absent
ruff check src tests: passed
mypy src: no issues in 64 source files
python -m build: wheel and source distribution built successfully
git diff --check: passed
```

Live provider smoke and benchmark execution remain operator-only and pending credentials. Capability numbers remain configured priors until measured by the benchmark command.

## Tranche N: Release Integrity And Product Differentiation

Baseline: Sol review of Tranche M at `5c9c1e5`. The review findings were accepted in `28c2a5e` before implementation. Each phase below was implemented with a failing-first regression and committed independently.

### Failing-first checkpoints

```text
N.1: forced ZIP validation failure still produced a delivered result and receipt
N.2: the default pipeline broker was not bound to the run SQLite store; stale reservations could be reused; unknown headers erased exact windows
N.3: when every handoff candidate failed, the synthesis task failed without a grounded fallback
N.4: claim verification saw unconsumed chunks and contradicted claims remained citation-eligible
N.5: chapter nodes had no chapter contract, emitted generic identical extractive summaries, and the model prompt had no chapter objective
N.6: rendered validation inspected only page one and leaked temporary render directories on failure
```

### Implemented

- Made delivery finalization atomic at the product boundary: ZIP inventory, CRC, manifest, checksums, quality state, and receipt now agree. A failed ZIP demotes the run and cannot receive a receipt.
- Bound the default capability registry to the durable runtime store. Capacity observations retain latest raw observations separately from effective windows; local commits cannot consume against a newer provider snapshot.
- Added a grounded `extractive_provider_fallback` after all eligible provider handoffs are exhausted. Non-handoffable failures still fail honestly.
- Scoped claim verification to chunks consumed by the task, separated structural support from citation eligibility, and rendered contradicted claims under `Rejected Claims` without citing them.
- Added stable run-type-specific chapter contracts for research, repository, code review, and general work. Chapter IDs, titles, and objectives flow through the DAG, deterministic workers, model prompts, final reports, and PPTX slides.
- Rendered every PDF/DOCX/PPTX page, computed a visible-content floor per page, generated a temporary contact sheet for inspection, preserved structural validation as blocking, and cleaned render output on every exit path.
- Updated the disposition ledger, README disclosures, and this implementation log. Capability scores remain configured priors; live provider quality and semantic entailment remain explicitly unproven/deferred.

### Verification gate (2026-07-12, no keys and no live provider calls)

```text
unittest discover: 222 tests passed
evals --run: 3/3 passed
doctor: passed with all provider credentials absent
ruff check src tests: passed
mypy src: no issues in 64 source files
python -m build: wheel and source distribution built successfully
git diff --check: passed before documentation changes
fixture key-sweep and local_only-with-keys regressions: passed within the suite
```

### Operator live evidence

Still pending by design. The operator must add credentials or authenticate official subscription CLIs locally, run one sanctioned smoke per configured provider, and run one real benchmark. Those results belong under the existing `Operator Live Evidence` section and must not be inferred from fixture results.

## Tranche O.0: Core Product Boundary Regressions

Baseline: `dcb3eaa`, with the scope target set to the report-defined core product above 90 percent. The six accepted residuals were pinned before implementation.

Failing-first transcript:

```text
tests.test_tranche_o0_boundaries: 6 boundary tests discovered
4 failures and 2 errors
- INSUFFICIENT verifier result was delivered and citation-eligible
- late ZIP demotion left final_report.md claiming Quality passed: True
- ZIP construction exceptions escaped finalization
- renderer accepted fewer pages than the source artifact
- render timeout escaped and left temporary output
- model-enabled chapter nodes 002/003 remained extractive
```

The failing-first tests are retained in `tests/test_tranche_o0_boundaries.py`. The disposition ledger is `docs/reviews/2026-07-13-tranche-o-disposition.md`; no existing gate was weakened.
