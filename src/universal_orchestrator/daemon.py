from __future__ import annotations

from pathlib import Path

from universal_orchestrator.models import HostInvocation
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.routing import CapabilityRegistry


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
        result = Orchestrator(Path(".uo/runs")).run(invocation)
        return result.model_dump(mode="json")

    return app


app = create_app()

