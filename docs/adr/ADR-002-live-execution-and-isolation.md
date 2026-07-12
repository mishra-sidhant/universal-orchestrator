# ADR-002: Live Execution And Isolation

- Status: Accepted
- Date: 2026-07-11
- Scope: Provider HTTP execution, accounting, timeout containment, and late completion

## Context

Tranche F introduces real OpenAI, Anthropic, and Ollama I/O. The kernel must bound network time and spend without adding a process boundary that does not itself improve containment for ordinary blocking HTTP. The Tranche E scheduler already owns a task completion lease, but provider accounting creates a new side effect that must be fenced after lease expiry.

## Decision

Provider adapters use an injected `HTTPTransport`. `UrllibHTTPTransport` performs one socket operation with the task's hard timeout; `FakeTransport` and specialized test transports exercise behavior without sockets. Provider policy above transport classifies failures as `auth`, `rate_limit`, `transient`, `fatal`, `timeout`, or `malformed_output`. Only rate-limit, transient, and timeout failures receive bounded exponential backoff with jitter; numeric `Retry-After` takes precedence. Auth, fatal, and malformed transport output fail immediately.

Provider calls remain in-process I/O. Containment has two deadlines:

1. The socket timeout normally terminates blocked network I/O.
2. The scheduler completion lease remains authoritative if a transport ignores its socket deadline.

The completion guard supports timeout cleanup registration and an atomic `commit_if_active` operation. Cost authorization registers immediate reservation release. Actual usage can commit only while the lease lock is active. A response arriving after timeout cannot add a ledger row, trigger the model reformat request, populate a worker result, write cache state, or reach an observer. The run continues through explicit failed-task handling and closes `needs_attention` when required quality cannot be established.

No general subprocess isolation is added for provider HTTP. It would add lifecycle and secret-transfer complexity while the load-bearing side effects are already fenced and the operation is I/O-bound.

## Budget-Stop Semantics

The default live ceiling is $0.50. Before transport, the thread-safe ledger reserves the configured estimate against actual spend plus concurrent reservations. If the estimate exceeds remaining budget, it records task, provider, model, estimate, remaining amount, and reason, raises `BudgetStopError`, and makes no model request. The pipeline copies the stop into `cost_ledger.json` and `budget_report.json`, adds an explicit quality violation, and terminates `needs_attention`. It never converts a budget stop into extractive success.

Provider-reported actual tokens commit after a successful response. Estimate/actual divergence is a calibration warning, not a retrospective budget gate or output-quality claim.

## Evidence

`test_hung_transport_times_out_releases_reservation_and_cannot_commit_late` uses a fake transport that deliberately ignores its request timeout. The synthesis task lease expires after one second. At run close:

- state is `needs_attention`;
- the schedule records the synthesis timeout;
- reserved cost is zero;
- provider call rows are empty.

The test then releases a valid late model response. The in-memory ledger remains empty and request count proves no reformat call occurred. This demonstrates the scheduler lease covers the identified uncooperative-I/O case.

## Revisit Triggers

Use stronger, case-specific containment if live execution later includes CPU-bound model code, native extensions with unsafe failure modes, repository-controlled plugins, subprocess tools, or a side effect that cannot participate in completion-guard cleanup and atomic commit. Such work requires a new ADR or amendment and its own kill/late-commit proof; this decision must not be generalized silently beyond provider I/O.

## Consequences

- Default and CI tests stay credential-free and socket-free.
- Real provider calls have both socket and task deadlines.
- Late threads may finish in memory, but cannot commit kernel-owned state.
- Cost reservations cannot remain stranded after scheduler timeout.
- The containment proof is executable and tied to the same transport interface used by production adapters.

## Tranche N Clarifications

Delivery finalization is a second, independent side-effect fence: a provider response may not become a delivered product unless the final manifest, checksums, ZIP inventory, quality state, and receipt agree. ZIP validation failure removes any stale receipt and terminates the run as `needs_attention`.

Provider capacity is durable but epistemically scoped. Exact windows may be reserved only against the effective snapshot that authorized the reservation; a newer snapshot prevents local decrement against stale state. Headerless or otherwise unknown observations are retained as observations and do not erase a previously known exact window. Unknown remains unknown, never unlimited.
