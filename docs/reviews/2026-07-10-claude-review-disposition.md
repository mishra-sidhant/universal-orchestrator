# July 10 Adversarial Review Disposition

Review baseline: `3e74812`. Status is updated phase by phase; `pending` rows are explicit remaining Tranche E work, not silent acceptance.

| Finding | Status | Commit | Evidence / disposition |
| --- | --- | --- | --- |
| 1a real pipeline and simulated static DAG diverge | pending E.2 | pending | Stage-worker registry and ADR-001 required. |
| 1b deterministic adapter only echoes completion | pending E.2 | pending | Real dispatch or truthful `SKIPPED` required. |
| 1c hardcoded planner and synthetic quality scores | partially fixed E.1 | pending E.2 | Synthetic quality names removed in E.1; plan scoring remains. |
| 2a global chunk fallback fabricates evidence | fixed E.1 | pending | `test_empty_task_pack_does_not_fallback_to_global_chunks`. |
| 2b worker refs are stamped without consumption | partially fixed E.1 | pending E.5 | Per-task consumed-ref contract enforced locally; adapter payload content plumbing remains. |
| 2c auditor verifies its own generated citations | fixed E.1 | pending | Valid-but-unconsumed mutation and exact unsupported-task tests. |
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
| 5c reported parallelism is not executed | pending E.2 | pending | Remove fictional telemetry or implement bounded execution. |
| 5d retries are dormant | pending E.4 | pending | One real retry policy plus flaky pipeline test, or delete. |
| 5e SQLite lacks WAL/busy timeout | pending E.4 | pending | Connection configuration test required. |
| 5f MCP cannot cancel inline run; malformed JSON kills loop; notifications answered | pending E.4 | pending | Protocol and concurrency tests required. |
| 5g states are unused/overloaded and receipts contradict failure | partially fixed E.0 | pending E.4 | `needs_attention` added and receipt withheld; real stage transitions/dead-state removal remain. |
| 6a routing cannot reshape/pause due fictional local capabilities | pending E.2 | pending | Truthful capabilities and unreachable-branch test required. |
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
