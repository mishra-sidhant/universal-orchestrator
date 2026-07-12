# Testing

The first test layer uses `unittest` so the project can validate in a clean Python environment without installing dev extras.

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

Recommended milestone checks:

```bash
PYTHONPATH=src python -m universal_orchestrator doctor
PYTHONPATH=src python -m universal_orchestrator providers
PYTHONPATH=src python -m universal_orchestrator run "Create a serious product package from this repo" .
PYTHONPATH=src python -m universal_orchestrator run "Create a PDF product package" --artifact pdf .
PYTHONPATH=src python -m universal_orchestrator evals
PYTHONPATH=src python -m universal_orchestrator evals --run --case unsafe_archive
PYTHONPATH=src python -m universal_orchestrator status <run_id>
```

When optional dev dependencies are installed, add:

```bash
ruff check src tests
mypy src
pytest
python -m build
```

The CI workflow validates Python 3.11, 3.12, and 3.13 with compilation, Ruff, the full `unittest` suite, and source/wheel package builds.

Provider tests use recorded JSON fixtures through `FakeTransport`. The default suite requires no credential, never opens a provider socket, and never invokes the opt-in `smoke` command. Real smoke results are operator evidence and must be recorded separately in the implementation log.

## Tranche D Regression Coverage

- Privacy and egress policy is rechecked at routing and adapter execution boundaries.
- Failures and cancellations persist terminal state and diagnostics; failed runs resume under the same run ID.
- Scheduler retries, dependency skips, timeouts, and attempt records are verified.
- Cached results remain successful fragments, corrupt entries are quarantined, and source references stay stable across runs.
- Manifest/checksum/ZIP/receipt hashes are recomputed and ZIP inventory is inspected.
- Extracted source tail content, chunk locators, final citations, and claim resolution are verified.
- Eval mutation tests prove malformed DAGs, incomplete routing, and damaged worker schemas fail their gates.

Tranche F validated baseline on July 11, 2026: 157 tests passing without keys or provider sockets, Ruff clean, all three built-in world-readiness eval cases passing, fixture bench green, and both sdist and wheel building successfully. That historical baseline carried a visible typing backlog.

Current canonical verification on July 12, 2026: 198 tests pass without keys or provider sockets, Ruff passes, all built-in world-readiness eval cases pass, `mypy src` passes with strict mode and no disabled error codes, and the sdist/wheel build succeeds with the local Hatchling backend. The opt-in provider smoke and real benchmark remain operator evidence by design.
