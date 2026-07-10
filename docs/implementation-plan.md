# Implementation Plan

## Current Milestone

Tranche D hardens the kernel from a deterministic product demonstration into a trustworthy local runtime. The tranche is complete when a run can enforce authority, survive failure, reuse work without corrupting semantics, ground claims in source passages, and emit a cryptographically coherent delivery package.

- Context manifest.
- Ranked context cards.
- Product contract and definition of done.
- Execution DAG.
- Routing decisions.
- Quality report.
- Final report.
- Run manifest.

## Decisions

- Package name: `universal_orchestrator`.
- CLI command: `ai-team`, matching the report examples.
- Core dependency: Pydantic v2.
- Runtime surface: standard-library CLI now, optional Typer later.
- Daemon surface: optional FastAPI module with graceful missing-dependency errors.
- Tests: standard-library `unittest` now, optional pytest later.
- Persistence: local `.uo/runs/{run_id}` artifact directories.

## Tranche D Scope

1. Enforce privacy and egress authority independently from provider availability.
2. Persist failure/cancellation outcomes and support retries, timeouts, dependency failure, and same-ID resume.
3. Treat valid cache hits as successful results and quarantine corrupt/version-incompatible cache entries.
4. Select the most relevant prior successful run for delta planning.
5. Freeze payloads, manifest, checksums, ZIP, validation, and delivery receipt in a one-way finalization sequence.
6. Retain redacted extracted text, stable chunks, source locators, task-specific context, and claim-level citations.
7. Replace presence-only evals with schema validation, graph validation, cross-artifact reconciliation, and mutation tests.
8. Ship parser dependencies, multi-version CI, and release documentation.

## Done Criteria For This Milestone

- `PYTHONPATH=src python -m universal_orchestrator doctor` works.
- `PYTHONPATH=src python -m universal_orchestrator run "..." ./some-path` writes artifacts.
- Full unit tests, Ruff, built-in evals, compilation, and package construction pass.
- Delivery checksums recompute, the bundle contains the frozen manifest and integrity evidence, and the receipt matches the bundle hash.
- Source-required runs contain resolvable chunk citations and a Sources section.
- Documentation describes authority, lifecycle, evidence, delivery invariants, and remaining limitations.

## Next Tranche

- Validate live provider execution quality, structured response conformance, rate limits, fallback, and cost accounting once keys are supplied.
- Add bounded parallel scheduling with process isolation and cooperative cancellation of active provider requests.
- Add sandboxed archive extraction, OCR, media transcription, and larger-document streaming.
- Resolve the strict typing backlog in optional adapters and daemon/MCP boundaries, then promote `mypy src` into CI.
- Add signed receipts, migration tooling, retention policy, multi-tenant isolation, and deployment/upgrade testing.
