# July 11 Tranche E Re-Review Disposition

Review baseline: `82b2b59`. This ledger is the Tranche F resume point. `pending` means scheduled Tranche F work; explicit deferrals include a reason and are not silently accepted.

| Finding / phase item | Status | Commit | Evidence / disposition |
| --- | --- | --- | --- |
| R1 citation score is a keyword constant | fixed F.0 | 9260735 | `test_quality_engine_does_not_infer_citation_score_from_contract_keywords`; measured 1/2 ratio pinned at 50. |
| R2 final-citation finding is false before assembly | fixed F.0 | 9260735 | Pre-repair audit retained; persisted audit reruns post-assembly and agrees with delivered Sources. |
| R3 scheduler parallelism | deferred by operator scope | 82b2b59 | Current real DAG is linear and reports 1 honestly; parallel scheduling is explicitly next tranche. |
| R4 timeout containment for live I/O | pending F.6 | pending | ADR-002 and hung-transport proof required before tranche closure. |
| R5 mypy backlog | deferred, visible | e8c28e6 | Non-blocking CI baseline remains visible; live-path code must not increase the undisclosed backlog. |
| Minor `_summary` name collision | clarified F.0 | 9260735 | Removed `DeterministicExecutor._summary` was dead; `workers.py` `_summary` is the live structured-output formatter. |
| F.1 injectable transport and fixtures | fixed F.1 | 80a742c | `HTTPTransport`, `UrllibHTTPTransport`, and scripted `FakeTransport`; all adapters fixture-tested without sockets. |
| F.1 provider error taxonomy | fixed F.1 | 80a742c | Typed auth/rate-limit/transient/fatal/timeout/malformed-output failures; retries are bounded and limited to eligible kinds. |
| F.1 socket-level call timeout | fixed F.1 | 80a742c | Adapter task timeout is carried on each `HTTPRequest` and passed to `urlopen`, independently of the scheduler lease. |
| F.1 opt-in smoke command | fixed F.1 | 80a742c | `ai-team smoke --provider`; fixed tiny prompt, explicit key gate, latency and usage output. USD remains unset until F.3 rates. |
| F.2 outbound redaction | fixed F.2 | f053b00 | Planted source and metadata key are absent from the captured request body; redaction marker is present. |
| F.2 injection quarantine and delimiters | fixed F.2 | f053b00 | Compiler and renderer both exclude the hostile chunk; retained context has authority preamble and begin/end delimiters. |
| F.2 local-only with keys | fixed F.2 | f053b00 | Valid key/model, network authority, live adapter, and forged route still produce zero fake-transport requests. |
| F.2 full key sweep | fixed F.2 | f053b00 | Live-configured full run scans every run artifact and every delivery ZIP member for planted key material; zero matches. |
| F.3 pre-call cost gate | fixed F.3 | b54c2a0 | Thread-safe reservation stops before transport and records task, provider, model, estimate, remaining budget, and reason. Default pinned at $0.50. |
| F.3 actual usage ledger | fixed F.3 | b54c2a0 | Fixture-reported 11 input/7 output tokens price to $0.000160 and persist with model and rate provenance. |
| F.3 estimate/actual reconciliation | fixed F.3 | b54c2a0 | `budget_report.json` carries estimate/actual fields; threshold divergence adds recalibration warning without failing quality. |
| F.3 configurable rate table | fixed F.3 | b54c2a0 | Packaged `provider_rates.json` has version, provider defaults, exact-model slots, and documented update procedure. |
| F.4 model-backed synthesis | fixed F.4 | d10f3bd | Premium, policy-permitted synthesis routes to fixture OpenAI with bounded pack; strict claims enter the worker schema and final report labels the path. |
| F.4 schema validation, one repair, extractive fallback | fixed F.4 | d10f3bd | Tests pin direct success, one-repair success, and two-malformed-response extractive fallback with exactly two model calls. |
| F.4 model-claim evidence discipline | fixed F.4 | d10f3bd | Fabricated ref makes claim unsupported and run `needs_attention`; low lexical overlap is explicitly warning-only and not entailment. |
| F.4 real provider routing with keyless default | fixed F.4 | d10f3bd | Complete configuration selects model capability; keyless run remains extractive with zero provider calls. |
| F.5 cached provider health | fixed F.5 | `Tranche F.5: add measured health and fallback modes` | Fixture probes classify healthy/degraded/down, carry socket timeout, cache for TTL, and persist measured health for routing. |
| F.5 provider-family fallback and actionable pause | fixed F.5 | `Tranche F.5: add measured health and fallback modes` | OpenAI-down routes Anthropic; all-hosted-down stays extractive with report notice; pause names capability and configuration action. |
| F.5 Ollama parity | fixed F.5 | `Tranche F.5: add measured health and fallback modes` | Ollama uses `/api/tags`, shared transport/error/cost machinery, structured synthesis, and a fixture-verified $0 actual row. |
| F.6 containment decision | pending | pending | ADR-002 plus hung-transport late-commit test. |
| F.7 fixture-backed bench | pending | pending | Native and orchestrated outputs/cost/latency emitted side by side. |
| F.7 no automated superiority claim | pending | pending | README and artifact wording remain measurement-only. |
| F.7 operator-only real bench | pending | pending | Keys and real network remain outside agent/CI execution. |

## Test Rewrites

F.0 adds new regressions and does not weaken or delete an existing assertion.

F.1 replaces `test_http_provider_retries_429_and_5xx`, which patched `urllib` internals, with the same guarantee at the new injectable transport boundary. The replacement additionally asserts request count and exact `Retry-After` delay without permitting a socket. No failure expectation was removed.

F.2 adds four new security regressions and does not weaken or delete an existing assertion.

F.3 adds five accounting regressions and does not weaken or delete an existing assertion.

F.4 adds seven model-path regressions and does not weaken or delete an existing assertion.

F.5 adds five operating-mode regressions. F.2/F.4 transport-count assertions were refined to distinguish bounded liveness probes from model calls; `local_only` still asserts zero total calls, and pre-call budget enforcement still asserts zero model invocations.
