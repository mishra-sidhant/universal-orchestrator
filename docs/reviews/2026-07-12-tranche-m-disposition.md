# Tranche M Disposition

Review baseline: the Sol review of the Tranche G implementation. This table is the resume point for the reliability and product-quality closure work.

| Finding / tranche item | Status | Evidence |
| --- | --- | --- |
| Exact request and total-token capacity enforcement | fixed | Provider authorization now reserves `REQUESTS=1` and `TOTAL_TOKENS=input+output`; `test_provider_authorization_reserves_request_and_total_token_dimensions` proves the second call is stopped before transport. |
| Expired capacity telemetry contradiction | fixed | `CapacityBroker.effective_status()` reports expired observations as `unknown`; routing telemetry uses the effective status. |
| Subscription call limits | fixed | Default local ceiling is 12, configurable only downward by operator input, reserved before CLI execution, persisted in SQLite, released on failed calls, and retained on commit. |
| Checkpoint persistence without resume consumption | fixed | Scheduler restores exact-fingerprint cacheable checkpoints and records `checkpoint_hits`; side-effecting tasks rerun. |
| Multi-hop handoff | fixed | Fixture proves provider-a failure -> provider-b failure -> provider-c success with two durable handoff records and three attempts. |
| Contradiction/semantic verification boundary | fixed | Injectable verifier is wired into the evidence audit; contradictions block, default structural verification remains `unknown` and non-entailment. |
| OCR/transcript security audit loss | fixed | Raw media text is scanned before redaction; redacted text is the only persisted content. |
| Cosmetic single-chapter product plan | fixed | Three executable chapter tasks fan out from gap analysis and artifact construction depends on all three. |
| Artifact validation bypass | fixed | Validation errors and render failures update final quality before state/receipt; forced PDF validation test ends `needs_attention` with no receipt. |
| Render-aware rich artifacts | fixed | PPTX is chapter-based, wraps body text, creates continuation slides, checks bounds, and runs bitmap preview checks with quality-tier behavior. |
| Full semantic entailment | deferred by explicit boundary | No semantic verifier is claimed by default. A configured verifier is supported through the injectable protocol; the default lexical floor remains warning-only. |
| Live provider quality and quota truth | pending operator evidence | No agent or CI call uses credentials. Operator must run smoke once per configured provider and one real bench after adding keys in root `.env.local`. |
| Parallel fan-out execution | fixed in this tranche | Scheduler already executes independent ready batches through a bounded thread pool; the chapter DAG now creates a real parallel batch. |
