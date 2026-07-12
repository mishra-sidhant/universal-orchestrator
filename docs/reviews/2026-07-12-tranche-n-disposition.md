# Tranche N Disposition

Review baseline: Sol review of Tranche M at commit `5c9c1e5`. Every row below is accepted and is a required implementation item unless explicitly marked deferred.

| Finding | Status | Evidence |
| --- | --- | --- |
| ZIP validation can issue a receipt after failure | accepted and fixed | `92f66ce`; `tests.test_tranche_n1_delivery` forces ZIP failure and asserts `needs_attention` with no receipt, then asserts valid manifest/ZIP agreement |
| Default pipeline does not bind SQLite to the capacity broker | accepted and fixed | `eb238c7`; `tests.test_tranche_n2_capacity.test_registry_runtime_binding_reaches_broker` |
| Committed capacity can be reused against stale snapshots | accepted and fixed | `eb238c7`; `tests.test_tranche_n2_capacity.test_committed_capacity_is_not_reused_against_same_snapshot` |
| Headerless observations can erase exact capacity windows | accepted and fixed | `eb238c7`; `tests.test_tranche_n2_capacity.test_headerless_unknown_observation_does_not_erase_exact_window` |
| Chapter tasks produce indistinguishable generic output | accepted and fixed | `62b00c9`; `tests.test_tranche_n5_chapters` pins run-type templates, chapter metadata, distinct extractive output, and model objectives |
| Render validation inspects only the first page/slide | accepted and fixed | `806b81b`; `tests.test_tranche_k1_artifacts.test_render_validation_inspects_every_page_and_cleans_temp_output` detects a blank second page and verifies cleanup |
| Exhausted handoff candidates do not use grounded fallback | accepted and fixed | `6ca8a4e`; `tests.test_tranche_h2_handoff.test_all_handoff_candidates_exhausted_uses_grounded_extractive_fallback` |
| Claim verification receives unconsumed chunks | accepted and fixed | `6aaaab6`; `tests.test_tranche_i2_verification.test_verifier_receives_only_task_consumed_chunks` |
| Contradicted claims remain citation-eligible | accepted and fixed | `6aaaab6`; `tests.test_tranche_i2_verification.test_contradicted_claim_is_not_citation_eligible` and the pipeline report mutation fixture |
| Live provider quality and semantic entailment | explicitly deferred | Requires operator smoke/bench and an explicitly configured semantic verifier |

## Phase Ledger

| Phase | Status | Commit | Verification |
| --- | --- | --- | --- |
| N.0 review disposition | complete | `28c2a5e` | Accepted every finding and recorded explicit live-quality/entailment deferrals |
| N.1 atomic delivery finalization | complete | `92f66ce` | 28 targeted tests; ZIP failure cannot issue a receipt |
| N.2 durable capacity reconciliation | complete | `eb238c7` | 13 capacity/runtime tests; stale and unknown observations pinned |
| N.3 grounded exhausted-provider fallback | complete | `6ca8a4e` | Handoff suite passes; all candidates exhausted still returns grounded extractive output |
| N.4 scoped verification and citation eligibility | complete | `6aaaab6` | 6 verification tests plus the F.4 evidence suite |
| N.5 differentiated product chapters | complete | `62b00c9` | 4 chapter-contract tests; planner, workers, prompts, report, and slides share metadata |
| N.6 full rendered-page validation | complete | `806b81b` | 5 artifact tests; blank second page blocks serious quality and temp output is removed |
| N.7 docs and final gates | complete | this documentation commit | 222 tests, evals, doctor, ruff, mypy, build, and diff checks passed |

## Release Gate

The default suite remained credential-free and socket-free. The final committed-tree gate on 2026-07-12 passed with 222 tests, 3/3 eval cases, doctor with provider credentials absent, ruff, mypy across 64 source files, and an sdist plus wheel build. Fixture key-sweep and `local_only` regressions remain green in the suite. Real provider smoke and benchmark execution remain operator-only and are not represented as completed evidence.
