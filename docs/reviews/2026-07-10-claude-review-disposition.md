# July 10 Adversarial Review Disposition

Review baseline: `3e74812`. Every row is closed as fixed or explicitly deferred; deferred work includes its scope rationale and the commit that documented the decision.

| Finding | Status | Commit | Evidence / disposition |
| --- | --- | --- | --- |
| 1a real pipeline and simulated static DAG diverge | fixed E.2 with documented boundaries | 18670f9 | Five registered real stages; ADR-001 records pre/post-DAG residuals. |
| 1b deterministic adapter only echoes completion | fixed E.2 | 18670f9 | Adapter skip test and default-report no-echo test. |
| 1c hardcoded planner and synthetic quality scores | fixed E.2 | 18670f9 | E.1 score schema; E.2 contract-coverage mutation changes plan score. |
| 2a global chunk fallback fabricates evidence | fixed E.1 | 05790dd | `test_empty_task_pack_does_not_fallback_to_global_chunks`. |
| 2b worker refs are stamped without consumption | fixed E.1/E.5/E.6 | 05790dd / a1ab9f6 / e8c28e6 | Bounded packs enter provider previews; only synthesis declares source evidence and carries consumed refs. |
| 2c auditor verifies its own generated citations | fixed E.1 | 05790dd | Valid-but-unconsumed mutation and exact unsupported-task tests. |
| 2d no semantic entailment check | deferred: hosted-quality scope | 05790dd | `citation_support` is explicitly documented as consumed-reference coverage; factuality field removed. |
| 3a post-repair continuity/completeness denominator crash | fixed E.0 | fcbb77b | `test_post_repair_quality_rates_use_original_and_repair_task_union`; pipeline repair regression. |
| 3b pass-description appears as violation | fixed E.0 | fcbb77b | `test_failed_execution_finding_uses_failure_description`. |
| 3c evidence audit occurs after repair | fixed E.0 | fcbb77b | Recording-order assertion in pipeline repair regression. |
| 3d audited and delivered product assembled separately | fixed E.0 | fcbb77b | Pipeline regression asserts one product assembly. |
| 3e repair bypasses scheduler | fixed E.0 | fcbb77b | Pipeline regression observes second scheduler call; repair attempts persisted. |
| 4a raw prompt secret persisted at three leak sites | fixed E.0 | fcbb77b | `test_secret_in_prompt_never_reaches_files_or_delivery_zip`. |
| 4b common secret patterns missing | fixed E.3 | 0aa1437 | Nine-family table test includes JSON and dotenv quoting. |
| 4c npm/cargo allowlist executes untrusted code with parent env | fixed E.3 | 0aa1437 | Auto-detection/allowlist removed; child-env capture test. |
| 4d URL fetch permits SSRF and policy is dead | fixed E.3 | 0aa1437 | Scheme/IP/DNS/override tests and pre-network ingestion test. Dead policy helpers deleted. |
| 4e archive scans only first 50 entries | fixed E.3 | 0aa1437 | Entry-61 traversal and tar link tests. |
| 4f `_safe_payload` is a no-op | fixed E.3 | 0aa1437 | Recursive payload redaction test. |
| 4g injection-risk content remains citable | fixed E.3/E.6 | 0aa1437 / e8c28e6 | Hostile chunks are excluded while safe chunks in the same source remain citable. |
| 5a orchestrator executor is shared mutable run state | fixed E.4 | be52ac8 | Obsolete field removed; concurrent two-run isolation test. Daemon creates per-request orchestrators. |
| 5b timed-out task thread continues after failure | fixed to documented guard boundary E.4 | be52ac8 | Cooperative completion lease fences scheduler cache/record/observer commits; process isolation remains a documented stronger option. |
| 5c reported parallelism is not executed | fixed E.2 for current plan | 18670f9 | Real DAG is linear and plan simulation reports max parallelism 1; bounded concurrency remains future work. |
| 5d retries are dormant | fixed E.4 | be52ac8 | Artifact build has two attempts; flaky real-pipeline test records failed then completed attempts. |
| 5e SQLite lacks WAL/busy timeout | fixed E.4 | be52ac8 | Every connection verifies WAL and at least 5,000 ms busy timeout. |
| 5f MCP cannot cancel inline run; malformed JSON kills loop; notifications answered | fixed E.4 | be52ac8 | Parse, notification, and active-run cancellation concurrency tests. |
| 5g states are unused/overloaded and receipts contradict failure | fixed E.0/E.4 | fcbb77b / be52ac8 | Receipt semantics fixed; real repair/post-DAG transitions emitted; three dead states removed. |
| 6a routing cannot reshape/pause due fictional local capabilities | fixed E.2 | 18670f9 | Strategic capability mutation reaches RESHAPE/PAUSE. |
| 6b context packs never reach providers | fixed dry-run plumbing E.5 | a1ab9f6 | Bounded previews for all adapters; reconciled usage ledger; configurable Anthropic output; 429/5xx retry scaffold. |
| 6c repository ingestion reads no file bodies | fixed E.5 | a1ab9f6 | A real source body becomes a path-located chunk and delivered citation. |
| 6d flagship report prompt is misclassified as repo implementation | fixed E.5 | a1ab9f6 | Explicit report/research/PDF intent precedes repo presence. |
| 6e non-ASCII terms are invisible | fixed E.5 | a1ab9f6 | Devanagari relevance and tight-budget retrieval test. |
| 6f delta duplicates cache checks; semantic naming overstates exact cache | fixed E.5 | a1ab9f6 | Renamed `ExactMatchCache`; delta delegates validation to scheduler API. |
| 6g timestamps are near-zero defaults | fixed E.2/E.5 | 18670f9 / a1ab9f6 | Stage workers and provider-backed executor set measured boundaries. |
| 6h timestamp-only IDs can collide | fixed E.5 | a1ab9f6 | Random suffix; 500 IDs remain unique under frozen time. |
| 6i JSON writes are non-atomic | fixed E.5 | a1ab9f6 | Temporary write, flush/fsync, atomic replace, failure-preserves-old-file test. |
| 6j dead artifact/executor code | fixed E.5 | a1ab9f6 | Removed stale artifact report renderer and executor summary. |
| 6k PDF builder fails on markup characters and mishandles H2 | fixed E.5 | a1ab9f6 | HTML escaping and Heading2 rendering; extracted-PDF regression. |
| E.6 bare-host bootstrap and proof | fixed E.6 | e8c28e6 | `uv.lock`, README commands, CI 3.11-3.13, non-blocking mypy, warning-free uv tests, accepted proof run. |
| Static typing backlog | deferred, visible | e8c28e6 | Non-blocking CI runs `mypy src`; baseline is 79 errors in 19 files. Promotion to blocking waits for adapter/optional-library typing cleanup. |
| E.0 receipt semantics for quality failure | fixed E.0 | fcbb77b | `test_quality_failed_run_needs_attention_without_delivery_receipt`. |

## Rewritten Existing Tests

No existing assertion was weakened or deleted in E.0. New regression coverage was added. Successful-delivery receipt tests remain unchanged; the new test covers the distinct quality-failed terminal path.

E.1 deliberately rewrote fixture fields in `test_repair.py` and `test_world_readiness.py` to the honest `QualityScore` schema, and changed `test_workers.py` from legacy `input_refs` to `consumed_chunk_refs`. The behavioral assertions remain equally strict; the implicit evidence fallback was removed rather than preserved.

E.2 deliberately rewrote six stale assumptions: budget capping now pins the real all-free DAG; repair routing expects reshape/pause for unimplemented work; deterministic capability tests reject fictional reasoning; repeat-cache coverage expects the three pure stages; planner tests use `T-AGGREGATE`; and E.0 failure injection raises inside the real handler. These changes strengthen truthfulness and do not delete a failure gate.

E.3 removed the old world-readiness assertions for test-only path/archive policy helpers because the operator required deletion of unused policy APIs. Live archive and URL boundaries now have materially stronger tests.

E.4 removed three enum members that had no runtime transition. No behavioral assertion was weakened; new tests cover live state attribution and protocol behavior.

E.5 rewrites four test imports from the overstated `SemanticCache` name to `ExactMatchCache`; cache behavior assertions are unchanged. No existing behavioral test was deleted or relaxed.

E.6 closes direct SQLite and HTTPError test fixtures and adds evidence/provenance/bootstrap regressions. No existing assertion was weakened or deleted.
