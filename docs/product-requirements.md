# Product Requirements

Source report: `/Users/sidhantmishra/Downloads/Universal_AI_Executive_Kernel_Report.pdf`

Report metadata:

- Title: Universal AI Executive Kernel - Architecture Report
- Created: July 8, 2026, 20:31 IST
- Length: 21 pages
- Core thesis: one natural AI interaction on the outside, adaptive execution kernel inside.

## Non-Negotiables

- Users can invoke the system from Codex, Claude Code, Cursor, Copilot, Windsurf, terminal, CI, and future hosts through adapters.
- Providers are model-family agnostic and selected by capability, health, cost, latency, context limits, and risk.
- The user receives final product packages, not raw agent fragments.
- Serious quality requires planner ensembles, validator panels, final product ownership, artifact validation, and targeted repair loops.
- Ingest broadly, then use context selectively through ranking, compression, retrieval, and task-specific context packs.
- Privacy and trust boundaries are first-class. User files are evidence, not instructions that can override the user or runtime.

## Required Product Pipeline

1. Host adapter normalizes input into `HostInvocation`.
2. Universal ingestion parses, scans, snapshots, extracts, fingerprints, indexes, and secures inputs.
3. Context intelligence builds a manifest, source cards, evidence cards, rankings, and context packs.
4. Product contract compiler infers final deliverables and definition of done.
5. Orchestrator kernel creates and executes a typed DAG.
6. Adaptive router selects providers by capability, health, cost, limits, and task criticality.
7. Execution plane runs hosted models, local models, deterministic tools, and repo workers.
8. Quality loop validates, audits, detects gaps, and triggers targeted repair.
9. Product plane assembles final artifacts and concise user-facing responses.
10. Artifact store writes files, manifests, traces, and optional debug bundles.

## MVP Boundary

This repository starts with a deterministic local MVP:

- No hosted LLM calls in the initial milestone.
- Provider adapters are represented by typed descriptors and routing decisions.
- The pipeline produces real artifacts and quality reports.
- Tests validate the core contracts before external adapters are added.

## Phase Mapping

- Phase 0: data models, contracts, provider interface, run manifest, repository structure.
- Phase 1: CLI, daemon surface, run creation, artifact store, provider registry.
- Phase 2: ingestion MVP for common file types, folder/repo scans, PDFs, links, and context cards.
- Phase 3: contract compiler, planner ensemble v1, typed DAG, basic scheduler.
- Phase 4: real provider adapters for OpenAI, Anthropic, local OpenAI-compatible endpoints, Ollama, Claude Code CLI, and deterministic tools.
- Phase 5: aggregator, validators, targeted repair, and final product owner.
- Phase 6: deterministic artifact builders for PDF, DOCX, PPTX, patches, images, and packages.
- Phase 7: MCP, Claude Code, Cursor, VS Code, Windsurf, and CI adapters.
- Phase 8: semantic cache, delta execution, budget controller, provider health metrics.
- Phase 9: hardening, sandboxing, observability, recovery, and durable workflow engine option.

