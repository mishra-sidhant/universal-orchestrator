from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from universal_orchestrator.models import HostInvocation
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.routing import CapabilityRegistry
from universal_orchestrator.runtime import RuntimeStore
from universal_orchestrator.utils import read_json
from universal_orchestrator.models import new_id


DEFAULT_DAEMON_ROOT = Path(".uo/runs")
DAEMON_API_VERSION = "v1"
_DAEMON_WORKERS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="uo-daemon-run")


def daemon_artifacts(root: Path | str = DEFAULT_DAEMON_ROOT) -> dict[str, Any]:
    run_root = Path(root)
    runs = Orchestrator(run_root).list_runs()
    return {"root": str(run_root), "runs": [str(path) for path in runs]}


def daemon_status(run_id: str, root: Path | str = DEFAULT_DAEMON_ROOT) -> dict[str, Any]:
    run_root = Path(root)
    manifest_path = run_root / run_id / "run_manifest.json"
    payload: dict[str, Any] = read_json(manifest_path) if manifest_path.exists() else {"run_id": run_id}
    payload["runtime_snapshot"] = RuntimeStore(run_root / "runtime.sqlite3").resumable_snapshot(run_id)
    return payload


def daemon_cancel(
    run_id: str,
    reason: str = "User requested cancellation.",
    root: Path | str = DEFAULT_DAEMON_ROOT,
) -> dict[str, Any]:
    run_root = Path(root)
    return RuntimeStore(run_root / "runtime.sqlite3").request_cancel(run_id, reason)


def daemon_resume(run_id: str, root: Path | str = DEFAULT_DAEMON_ROOT) -> dict[str, Any]:
    return Orchestrator(Path(root)).resume(run_id).model_dump(mode="json")


def create_app(root: Path | str = DEFAULT_DAEMON_ROOT, auth_token: str | None = None) -> Any:
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException
    except Exception as exc:  # pragma: no cover - optional dependency boundary
        raise RuntimeError("FastAPI is not installed. Install with: pip install -e '.[daemon]'") from exc

    run_root = Path(root)
    expected_token = auth_token or os.getenv("AI_TEAM_DAEMON_TOKEN")
    app = FastAPI(title="Universal Orchestrator", version="0.1.0")

    def authorize(token: str | None = Header(default=None, alias="X-AI-Team-Token")) -> None:
        if expected_token and token != expected_token:
            raise HTTPException(status_code=401, detail="Valid X-AI-Team-Token is required.")

    @app.get("/health")
    @app.get("/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "api_version": DAEMON_API_VERSION}

    @app.get("/providers", dependencies=[Depends(authorize)])
    @app.get("/v1/providers", dependencies=[Depends(authorize)])
    def providers() -> list[dict[str, Any]]:
        return [provider.model_dump(mode="json") for provider in CapabilityRegistry.from_environment().providers]

    @app.post("/runs", dependencies=[Depends(authorize)])
    @app.post("/v1/runs", dependencies=[Depends(authorize)])
    def create_run(invocation: HostInvocation) -> dict[str, Any]:
        run_id = new_id("run")
        _DAEMON_WORKERS.submit(Orchestrator(run_root).run, invocation, run_id)
        return {
            "accepted": True,
            "run_id": run_id,
            "state": "received",
            "poll_with": f"/{DAEMON_API_VERSION}/runs/{{run_id}}",
        }

    @app.get("/runs/{run_id}", dependencies=[Depends(authorize)])
    @app.get("/v1/runs/{run_id}", dependencies=[Depends(authorize)])
    def get_run(run_id: str) -> dict[str, Any]:
        return daemon_status(run_id, run_root)

    @app.post("/runs/{run_id}/cancel", dependencies=[Depends(authorize)])
    @app.post("/v1/runs/{run_id}/cancel", dependencies=[Depends(authorize)])
    def cancel_run(run_id: str, reason: str = "User requested cancellation.") -> dict[str, Any]:
        return daemon_cancel(run_id, reason, run_root)

    @app.get("/artifacts", dependencies=[Depends(authorize)])
    @app.get("/v1/artifacts", dependencies=[Depends(authorize)])
    def artifacts() -> dict[str, Any]:
        return daemon_artifacts(run_root)

    @app.post("/runs/{run_id}/resume", dependencies=[Depends(authorize)])
    @app.post("/v1/runs/{run_id}/resume", dependencies=[Depends(authorize)])
    def resume_run(run_id: str) -> dict[str, Any]:
        return daemon_resume(run_id, run_root)

    return app

try:
    app = create_app()
except RuntimeError:  # pragma: no cover - optional dependency boundary
    app = None
