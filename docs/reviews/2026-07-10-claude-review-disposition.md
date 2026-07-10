# July 10 Adversarial Review Disposition

Review baseline: `3e74812`. Status is updated phase by phase; `pending` rows are explicit remaining Tranche E work, not silent acceptance.

| Finding | Status | Commit | Evidence / disposition |
| --- | --- | --- | --- |
| 1a real pipeline and simulated static DAG diverge | fixed E.2 with documented boundaries | pending | Five registered real stages; ADR-001 records pre/post-DAG residuals. |
| 1b deterministic adapter only echoes completion | fixed E.2 | pending | Adapter skip test and default-report no-echo test. |
| 1c hardcoded planner and synthetic quality scores | fixed E.2 | pending | E.1 score schema; E.2 contract-coverage mutation changes plan score. |
| 2a global chunk fallback fabricates evidence | fixed E.1 | 05790dd | `test_empty_task_pack_does_not_fallback_to_global_chunks`. |
| 2b worker refs are stamped without consumption | partially fixed E.1 | 05790dd / pending E.5 | Per-task consumed-ref contract enforced locally; provider payload content remains. |
| 2c auditor verifies its own generated citations | fixed E.1 | 05790dd | Valid-but-unconsumed mutation and exact unsupported-task tests. |
| 2d no semantic entailment check | deferred: hosted-quality scope | pending | `citation_support` is explicitly documented as consumed-reference coverage; factuality field removed. |
| 3a post-repair continuity/completeness denominator crash | fixed E.0 | fcbb77b | `test_post_repair_quality_rates_use_original_and_repair_task_union`; pipeline repair regression. |
| 3b pass-description appears as violation | fixed E.0 | fcbb77b | `test_failed_execution_finding_uses_failure_description`. |
| 3c evidence audit occurs after repair | fixed E.0 | fcbb77b | Recording-order assertion in pipeline repair regression. |
| 3d audited and delivered product assembled separately | fixed E.0 | fcbb77b | Pipeline regression asserts one product assembly. |
| 3e repair bypasses scheduler | fixed E.0 | fcbb77b | Pipeline regression observes second scheduler call; repair attempts persisted. |
| 4a raw prompt secret persisted at three leak sites | fixed E.0 | fcbb77b | `test_secret_in_prompt_never_reaches_files_or_delivery_zip`. |
| 4b common secret patterns missing | pending E.3 | pending | Quoted/JSON/dotenv/PAT/Google/Slack/JWT/private-key/URL tests required. |
| 4c npm/cargo allowlist executes untrusted code with parent env | pending E.3 | pending | Remove defaults or add explicit permission; scrub environment. |
| 4d URL fetch permits SSRF and policy is dead | pending E.3 | pending | Scheme, DNS, private-address, and allowlist tests required. |
| 4e archive scans only first 50 entries | pending E.3 | pending | Entry-51 traversal and tar link tests required. |
| 4f `_safe_payload` is a no-op | pending E.3 | pending | Implement redaction or delete safety-implying method. |
| 4g injection-risk content remains citable | partially fixed E.1 | pending E.3 | Only consumed pack refs can be cited; injection-risk exclusion remains. |
| 5a orchestrator executor is shared mutable run state | pending E.4 | pending | Two-run isolation test required. |
| 5b timed-out task thread continues after failure | pending E.4 | pending | Completion guard or process isolation required and documented in ADR-001. |
| 5c reported parallelism is not executed | fixed E.2 for current plan | pending | Real DAG is linear and plan simulation reports max parallelism 1; bounded concurrency remains future work. |
| 5d retries are dormant | pending E.4 | pending | One real retry policy plus flaky pipeline test, or delete. |
| 5e SQLite lacks WAL/busy timeout | pending E.4 | pending | Connection configuration test required. |
| 5f MCP cannot cancel inline run; malformed JSON kills loop; notifications answered | pending E.4 | pending | Protocol and concurrency tests required. |
| 5g states are unused/overloaded and receipts contradict failure | partially fixed E.0 | pending E.4 | `needs_attention` added and receipt withheld; real stage transitions/dead-state removal remain. |
| 6a routing cannot reshape/pause due fictional local capabilities | fixed E.2 | pending | Strategic capability mutation reaches RESHAPE/PAUSE. |
| 6b context packs never reach providers | pending E.5 | pending | Dry-run payload tests and usage fields required. |
| 6c repository ingestion reads no file bodies | pending E.5 | pending | Real-file chunk/citation test required. |
| 6d flagship report prompt is misclassified as repo implementation | pending E.5 | pending | Contract precedence test required. |
| 6e non-ASCII terms are invisible | pending E.5 | pending | Hindi relevance test required. |
| 6f delta duplicates cache checks; semantic naming overstates exact cache | pending disposition E.5 | pending | Consolidate or rename without adding telemetry. |
| 6g timestamps are near-zero defaults | pending disposition E.4/E.5 | pending | Real workers/stages must set measured times. |
| 6h timestamp-only IDs can collide | pending E.5 | pending | Random suffix and collision test required. |
| 6i JSON writes are non-atomic | pending E.5 | pending | Atomic replace test required. |
| 6j dead artifact/executor code | pending E.5 | pending | Remove after E.2 dispatch settles. |
| 6k PDF builder fails on markup characters and mishandles H2 | pending disposition E.5 | pending | Builder regression tests required or explicit deferral rationale before E.5 commit. |
| E.0 receipt semantics for quality failure | fixed E.0 | fcbb77b | `test_quality_failed_run_needs_attention_without_delivery_receipt`. |

## Rewritten Existing Tests

No existing assertion was weakened or deleted in E.0. New regression coverage was added. Successful-delivery receipt tests remain unchanged; the new test covers the distinct quality-failed terminal path.

E.1 deliberately rewrote fixture fields in `test_repair.py` and `test_world_readiness.py` to the honest `QualityScore` schema, and changed `test_workers.py` from legacy `input_refs` to `consumed_chunk_refs`. The behavioral assertions remain equally strict; the implicit evidence fallback was removed rather than preserved.

E.2 deliberately rewrote six stale assumptions: budget capping now pins the real all-free DAG; repair routing expects reshape/pause for unimplemented work; deterministic capability tests reject fictional reasoning; repeat-cache coverage expects the three pure stages; planner tests use `T-AGGREGATE`; and E.0 failure injection raises inside the real handler. These changes strengthen truthfulness and do not delete a failure gate.
