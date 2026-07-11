# July 11 Tranche E Re-Review Disposition

Review baseline: `82b2b59`. This ledger is the Tranche F resume point. `pending` means scheduled Tranche F work; explicit deferrals include a reason and are not silently accepted.

| Finding / phase item | Status | Commit | Evidence / disposition |
| --- | --- | --- | --- |
| R1 citation score is a keyword constant | fixed F.0 | `Tranche F.0: close citation honesty residuals` | `test_quality_engine_does_not_infer_citation_score_from_contract_keywords`; measured 1/2 ratio pinned at 50. |
| R2 final-citation finding is false before assembly | fixed F.0 | `Tranche F.0: close citation honesty residuals` | Pre-repair audit retained; persisted audit reruns post-assembly and agrees with delivered Sources. |
| R3 scheduler parallelism | deferred by operator scope | 82b2b59 | Current real DAG is linear and reports 1 honestly; parallel scheduling is explicitly next tranche. |
| R4 timeout containment for live I/O | pending F.6 | pending | ADR-002 and hung-transport proof required before tranche closure. |
| R5 mypy backlog | deferred, visible | e8c28e6 | Non-blocking CI baseline remains visible; live-path code must not increase the undisclosed backlog. |
| Minor `_summary` name collision | clarified F.0 | `Tranche F.0: close citation honesty residuals` | Removed `DeterministicExecutor._summary` was dead; `workers.py` `_summary` is the live structured-output formatter. |
| F.1 injectable transport and fixtures | fixed F.1 | `Tranche F.1: add bounded live transport substrate` | `HTTPTransport`, `UrllibHTTPTransport`, and scripted `FakeTransport`; all adapters fixture-tested without sockets. |
| F.1 provider error taxonomy | fixed F.1 | `Tranche F.1: add bounded live transport substrate` | Typed auth/rate-limit/transient/fatal/timeout/malformed-output failures; retries are bounded and limited to eligible kinds. |
| F.1 socket-level call timeout | fixed F.1 | `Tranche F.1: add bounded live transport substrate` | Adapter task timeout is carried on each `HTTPRequest` and passed to `urlopen`, independently of the scheduler lease. |
| F.1 opt-in smoke command | fixed F.1 | `Tranche F.1: add bounded live transport substrate` | `ai-team smoke --provider`; fixed tiny prompt, explicit key gate, latency and usage output. USD remains unset until F.3 rates. |
| F.2 outbound redaction | pending | pending | Fake transport must capture no planted secret. |
| F.2 injection quarantine and delimiters | pending | pending | Hostile chunks excluded; untrusted data visibly delimited. |
| F.2 local-only with keys | pending | pending | Hosted fake transport invocation count must remain zero. |
| F.2 full key sweep | pending | pending | Entire run directory and delivery ZIP scanned. |
| F.3 pre-call cost gate | pending | pending | Default ceiling remains $0.50; stop before unaffordable invocation. |
| F.3 actual usage ledger | pending | pending | Fixture token counts and actual costs persisted per call. |
| F.3 estimate/actual reconciliation | pending | pending | Divergence becomes a warning, not a false quality gate. |
| F.3 configurable rate table | pending | pending | Versioned provider/model pricing config and documented update path. |
| F.4 model-backed synthesis | pending | pending | Bounded pack with inline chunk IDs; structured result. |
| F.4 schema validation, one repair, extractive fallback | pending | pending | Malformed fixture degrades honestly after one reformat attempt. |
| F.4 model-claim evidence discipline | pending | pending | Fabricated ref fails; lexical overlap is warning-only and labeled weak. |
| F.4 real provider routing with keyless default | pending | pending | Hosted path covered by fixtures; Tranche E local path stays default without keys. |
| F.5 cached provider health | pending | pending | Healthy/degraded/down fixture states feed routing. |
| F.5 provider-family fallback and actionable pause | pending | pending | Final report names degraded mode; pause says what to configure. |
| F.5 Ollama parity | pending | pending | Same transport, taxonomy, ledger; zero-cost rows. |
| F.6 containment decision | pending | pending | ADR-002 plus hung-transport late-commit test. |
| F.7 fixture-backed bench | pending | pending | Native and orchestrated outputs/cost/latency emitted side by side. |
| F.7 no automated superiority claim | pending | pending | README and artifact wording remain measurement-only. |
| F.7 operator-only real bench | pending | pending | Keys and real network remain outside agent/CI execution. |

## Test Rewrites

F.0 adds new regressions and does not weaken or delete an existing assertion.

F.1 replaces `test_http_provider_retries_429_and_5xx`, which patched `urllib` internals, with the same guarantee at the new injectable transport boundary. The replacement additionally asserts request count and exact `Retry-After` delay without permitting a socket. No failure expectation was removed.
