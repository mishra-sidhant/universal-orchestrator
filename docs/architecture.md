# Architecture

Universal Orchestrator is arranged around the same planes as the source report.

## Host Plane

Hosts normalize their invocation into `HostInvocation`. The current CLI creates this object directly. Future adapters should preserve the same shape for Codex MCP, Claude Code slash commands, Cursor, VS Code, Windsurf, API, and CI.

Core model:

- `HostInvocation`
- `InputAttachment`
- `UserOptions`

## Ingestion Plane

The ingestion plane inventories everything the user supplies, but does not assume every input should enter model context. It fingerprints files, extracts summaries where safe, detects type, scans for secrets and instruction-like untrusted content, and emits a `ContextManifest`.

Implemented now:

- Prompt ingestion.
- Text, Markdown, code, and unknown text-like files.
- PDF text extraction through `pdfplumber` when available.
- Folder and repository scans with dependency/build/cache ignores.
- URL/API inventory without network fetch.
- Binary metadata records for images, Office documents, spreadsheets, archives, and media.

Planned:

- Structured DOCX, PPTX, spreadsheet, image OCR, archive sandbox, URL fetch snapshots, API schema inference, and audio/video transcription.

## Context Intelligence Plane

Context intelligence converts `InputRecord` values into `ContextCard` objects, ranks them against the prompt, and creates `ContextPack` values for task-specific execution.

Current ranking is deterministic lexical overlap plus specificity and risk boosts. Future ranking should add embeddings, recency, trust, freshness, authority, and semantic deduplication.

## Product Plane

The `ProductContractCompiler` converts messy prompts into a `ProductContract` and `DefinitionOfDone`. This is the source of truth for planning and validation.

The first compiler infers:

- Run type.
- Requested output.
- Primary and secondary artifacts.
- Must-have constraints.
- Must-not-have constraints.
- Artifact and validation gates.

## Orchestrator Kernel

The kernel uses `PlannerEnsemble` to create a typed `TaskDAG`. The first planner is deterministic but keeps the ensemble roles visible through tasks for strategy, decomposition, risk review, routing, execution, aggregation, gap analysis, final synthesis, quality, and packaging.

The DAG is validated for missing dependencies and cycles before routing.

## Routing Plane

`CapabilityRegistry` describes providers by capability, cost tier, health, context limits, and kind. `AdaptiveRouter` selects the best available provider or marks a task as degraded, reshaped, or paused.

Current providers:

- `deterministic.tools`: always available local tools.
- `openai.configured`: enabled only when `OPENAI_API_KEY` exists.
- `anthropic.configured`: enabled only when `ANTHROPIC_API_KEY` exists.
- `ollama.local`: enabled only when `OLLAMA_BASE_URL` exists.

No hosted provider calls are made in this milestone.

## Execution Plane

`DeterministicExecutor` records structured task outputs without external model calls. It is intentionally simple so the run manifest, quality gates, artifacts, and tests can be stabilized before provider side effects are introduced.

## Quality Plane

`QualityGateEngine` checks:

- Manifest completeness.
- DAG validity.
- Routing coverage.
- Pauses, reshapes, degraded work, skipped tasks, and failed tasks.
- Partial parsing.
- High-severity security findings.
- Artifact existence.

Future quality work should add contract-specific validators, citation audit, code test execution, final product owner review, and executable repair DAGs.

## Artifact Plane

`ArtifactStore` writes one run directory per run under `.uo/runs/{run_id}`. Each package includes:

- `context_manifest.json`
- `context_cards.json`
- `product_contract.json`
- `task_dag.json`
- `routing_decisions.json`
- `execution_results.json`
- `quality_report.json`
- `final_report.md`
- `run_manifest.json`

