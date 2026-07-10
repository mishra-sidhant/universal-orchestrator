# ADR-001: Kernel Unification

- Status: accepted and implemented in Tranche E.2
- Date: July 10, 2026
- Decision owner: human operator

## Context

Before Tranche E.2, the repository ran two systems. `_run_pipeline()` performed the real ingestion, quality, product, and artifact work. A static eleven-node DAG separately routed and scheduled deterministic adapter calls that returned only `"completed by local deterministic tools"`. Quality and evidence telemetry consumed those simulated results even though downstream work did not.

## Decision

Pipeline stages become the DAG. The local execution plan contains five nodes, each backed by a registered function:

1. `T-AGGREGATE`: counts and inventories indexed context.
2. `T-GAP-ANALYSIS`: computes partial-input, conflict, and security gaps.
3. `T-SYNTHESIS`: performs extractive synthesis from the chunks delivered to that task.
4. `T-ARTIFACT-BUILD`: writes the existing static run artifacts. It is side-effecting and non-cacheable.
5. `T-QUALITY`: invokes `QualityGateEngine` over the actual preceding stage results and built artifacts. It is non-cacheable.

`StageWorkerRegistry` is the dispatch boundary. Missing handlers return `SKIPPED` with an explicit reason. The generic deterministic provider adapter also returns `SKIPPED`; it can no longer manufacture completion.

The deterministic capability descriptor advertises only capabilities implemented by these stage functions. Routing eligibility requires every capability threshold to be met. Unimplemented strategic/model work therefore reaches `RESHAPE` or `PAUSE`.

## Necessary Pre-DAG Work

Ingestion, context indexing, contract compilation, plan construction, budget application, and routing remain pre-DAG. They define the inputs, shape, authority, and provider decision needed to execute the DAG; placing them inside that same DAG would be circular.

## Necessary Post-DAG Work

Final product rendering, requested PDF/DOCX/patch-plan construction, integrity audit, one-time manifest write, checksums, ZIP validation, and receipt issuance remain post-DAG. They require the completed schedule, evidence audit, final quality result, and complete artifact inventory. The Tranche D integrity order is unchanged.

## Residual Data-Flow Coupling

- The static artifact stage calls an injected function owned by `Orchestrator`; the registry does not own storage configuration.
- The quality stage receives an injected quality function and includes a provisional successful record for its own in-progress node. If evaluation raises, the actual node result is `FAILED`.
- Evidence adjustment and repair orchestration remain after the quality node. Repair tasks without a real registered handler reshape/skip and end `needs_attention`; they never echo-complete.
- Final format builders are not yet individual DAG nodes.
- Scheduler batches are executed sequentially. The five-node DAG is intentionally linear, so `max_parallelism=1` is truthful.
- Timeout execution remains thread-based until E.4 adds a late-completion guard.

## Cache Consequences

Aggregation, gap analysis, and extractive synthesis are pure and cacheable. Artifact construction and quality evaluation rerun for every run. The scheduler observes both executed and cached results, so quality sees the same real predecessor set on either path.

## Alternatives Considered

### Keep the simulated DAG until providers exist

Rejected. It made execution, quality, evidence, and plan telemetry claim work that did not occur.

### Delete the DAG and keep only the sequential pipeline

Rejected by operator decision. It would be more honest than the old system but would abandon the kernel's scheduling, cache, retry, cancellation, and degradation boundaries.

### Put every operation inside one DAG immediately

Rejected for this tranche. Ingestion/planning would create a circular graph, while receipt packaging cannot run before the final artifact inventory exists. The minimal truthful five-stage design is preferred over a larger nominal graph.

## Consequences

- Default final reports contain real measured/extractive stage summaries and no local-tool completion echoes.
- Plan scores derive from contract/DAG properties; they may fall when coverage is weak.
- Unsupported capabilities are visible as reshape/pause/skipped work.
- Only three pure stages can produce cache hits on an identical repeat run.
- The pipeline still coordinates pre/post boundaries, but there is one execution ontology: scheduled results correspond to functions that actually ran.
