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
PYTHONPATH=src python -m universal_orchestrator status <run_id>
```

When optional dev dependencies are installed, add:

```bash
ruff check .
mypy src
pytest
```
