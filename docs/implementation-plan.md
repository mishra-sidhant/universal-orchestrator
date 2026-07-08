# Implementation Plan

## Current Milestone

Build the kernel spine first. The first useful product should run locally, accept a natural prompt plus paths, and return a product package containing:

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

## Near-Term Engineering Tasks

1. Harden ingestion limits and archive safety.
2. Add DOCX/PPTX/XLSX structured parsers.
3. Add OpenAI-compatible provider adapter behind explicit credential checks.
4. Add Anthropic and Ollama adapters.
5. Add MCP tool wrapper for `ai_team.run`, `status`, `cancel`, `artifacts`, `configure`, `providers`, and `doctor`.
6. Add real repair DAG creation when quality gates fail.
7. Add artifact builders for PDFs and implementation reports.
8. Add cache keys for inputs, context cards, plans, and validation results.

## Done Criteria For This Milestone

- `PYTHONPATH=src python -m universal_orchestrator doctor` works.
- `PYTHONPATH=src python -m universal_orchestrator run "..." ./some-path` writes artifacts.
- Unit tests pass with `PYTHONPATH=src python -m unittest discover -s tests`.
- Documentation describes the product requirements, setup, and roadmap.

