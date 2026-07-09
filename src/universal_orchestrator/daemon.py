from __future__ import annotations

from pathlib import Path

from universal_orchestrator.models import HostInvocation
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.routing import CapabilityRegistry
from universal_orchestrator.runtime import RuntimeStore
from universal_orchestrator.utils import read_json


DEFAULT_DAEMON_ROOT = Path(".uo/runs")


def daemon_artifacts(root: Path | str = DEFAULT_DAEMON_ROOT) -> dict:
    run_root = Path(root)
    runs = Orchestrator(run_root).list_runs()
    return {"root": str(run_root), "runs": [str(path) for path in runs]}


def daemon_status(run_id: str, root: Path | str = DEFAULT_DAEMON_ROOT) -> dict:
    run_root = Path(root)
    payload = read_json(run_root / run_id / "run_manifest.json")
    payload["runtime_snapshot"] = RuntimeStore(run_root / "runtime.sqlite3").resumable_snapshot(run_id)
    return payload


def daemon_cancel(
    run_id: str,
    reason: str = "User requested cancellation.",
    root: Path | str = DEFAULT_DAEMON_ROOT,
) -> dict:
    run_root = Path(root)
    return RuntimeStore(run_root / "runtime.sqlite3").request_cancel(run_id, reason)


def create_app():
    try:
        from fastapi import FastAPI
    except Exception as exc:  # pragma: no cover - optional dependency boundary
        raise RuntimeError("FastAPI is not installed. Install with: pip install -e '.[daemon]'") from exc

    app = FastAPI(title="Universal Orchestrator", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/providers")
    def providers() -> list[dict]:
        return [provider.model_dump(mode="json") for provider in CapabilityRegistry.from_environment().providers]

    @app.post("/runs")
    def create_run(invocation: HostInvocation) -> dict:
        result = Orchestrator(DEFAULT_DAEMON_ROOT).run(invocation)
        return result.model_dump(mode="json")

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        return daemon_status(run_id, DEFAULT_DAEMON_ROOT)

    @app.post("/runs/{run_id}/cancel")
    def cancel_run(run_id: str, reason: str = "User requested cancellation.") -> dict:
        return daemon_cancel(run_id, reason, DEFAULT_DAEMON_ROOT)

    @app.get("/artifacts")
    def artifacts() -> dict:
        return daemon_artifacts(DEFAULT_DAEMON_ROOT)

    return app

try:
    app = create_app()
except RuntimeError:  # pragma: no cover - optional dependency boundary
    app = None
