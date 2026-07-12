# ADR-004: Durable Handoff And Headless Parallelism

Date: 2026-07-12
Status: Accepted

The local runtime remains SQLite-backed. Every task may hold one fenced lease identified by owner, lease ID, and monotonically increasing epoch. A result can become a durable checkpoint only while that lease is active; late workers and stale owners cannot commit.

The scheduler executes dependency-ready batches through a bounded thread pool, then performs cache writes, observer callbacks, result ordering, and checkpoint commits on the owner thread in deterministic task-ID order. This gives real overlap for independent I/O-bound work without making final artifacts depend on completion timing.

Provider handoff preserves task ID, context-pack identity, validated checkpoint sequence, and evidence rules. It changes only the provider attempt. Attempted connectors are excluded, the controller permits at most three attempts and two handoffs, and no available candidate yields an explicit failure or pause rather than an infinite retry loop.

The lease is sufficient for current in-process I/O and subprocess boundaries because socket/process deadlines and completion guards fence late results. CPU-bound untrusted extensions require a separate isolation decision.
