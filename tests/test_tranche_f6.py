from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from threading import Event
from time import sleep
from unittest.mock import patch

from universal_orchestrator.context import ContextIntelligence
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.models import (
    HostInvocation,
    InputAttachment,
    PrivacyMode,
    RunState,
    UserOptions,
)
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.planning import PlannerEnsemble
from universal_orchestrator.providers.transport import HTTPRequest, HTTPResponse
from universal_orchestrator.routing import CapabilityRegistry


class OneSecondSynthesisPlanner(PlannerEnsemble):
    def create_execution_plan(self, run_id, contract, model_synthesis=False):
        dag = super().create_execution_plan(run_id, contract, model_synthesis=model_synthesis)
        nodes = [
            node.model_copy(
                update={
                    "timeout_seconds": 1,
                }
            )
            if node.id == "T-SYNTHESIS"
            else node.model_copy(
                update={"required_capabilities": {"extractive_synthesis": 0.9}}
            )
            if node.id in {"T-CHAPTER-002", "T-CHAPTER-003"}
            else node
            for node in dag.nodes
        ]
        return dag.model_copy(update={"nodes": nodes})


class HungModelTransport:
    def __init__(self, model_response: HTTPResponse) -> None:
        self.model_response = model_response
        self.requests: list[HTTPRequest] = []
        self.model_started = Event()
        self.release_model = Event()
        self.response_returned = Event()

    def send(self, request: HTTPRequest) -> HTTPResponse:
        self.requests.append(request)
        if request.url.endswith("/models"):
            return HTTPResponse(200, {}, b'{"data": []}')
        self.model_started.set()
        self.release_model.wait(timeout=10)
        self.response_returned.set()
        return self.model_response


class TrancheF6ContainmentTests(unittest.TestCase):
    def test_hung_transport_times_out_releases_reservation_and_cannot_commit_late(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
            clear=True,
        ):
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("Late provider evidence must never commit after lease expiry.")
            request = HostInvocation(
                prompt="Produce a grounded timeout report",
                attachments=[InputAttachment(uri=str(source))],
                user_options=UserOptions(
                    allow_internet=True,
                    allow_cloud=True,
                    privacy_mode=PrivacyMode.CLOUD_ALLOWED,
                    budget_profile="premium",
                ),
            )
            manifest = InputIngestor().ingest(request, "run_probe")
            ref = next(
                chunk.id
                for chunk in ContextIntelligence().chunk_manifest(manifest)
                if chunk.input_id != "input_prompt"
            )
            structured = json.dumps(
                {
                    "summary": "This response arrived after the lease expired.",
                    "findings": [],
                    "claims": [
                        {
                            "text": "Late provider evidence must never commit.",
                            "evidence_refs": [ref],
                        }
                    ],
                    "manuscript": [
                        {
                            "heading": "Timeout Fixture",
                            "objective": "Prove late responses cannot commit.",
                            "body": "Late provider evidence must never commit.",
                            "evidence_refs": [ref],
                        }
                    ],
                }
            )
            model_response = HTTPResponse(
                200,
                {},
                json.dumps(
                    {
                        "id": "resp_late",
                        "model": "fixture-model",
                        "output_text": structured,
                        "usage": {
                            "input_tokens": 30,
                            "output_tokens": 20,
                            "total_tokens": 50,
                        },
                    }
                ).encode(),
            )
            transport = HungModelTransport(model_response)
            registry = CapabilityRegistry.from_environment(
                transports={"openai.configured": transport}
            )
            orchestrator = Orchestrator(root / "runs", capability_registry=registry)
            orchestrator.planner = OneSecondSynthesisPlanner()

            result = orchestrator.run(request)
            run_dir = Path(result.artifact_dir)
            ledger_at_close = json.loads((run_dir / "cost_ledger.json").read_text())
            schedule = json.loads((run_dir / "schedule_report.json").read_text())

            self.assertTrue(transport.model_started.is_set())
            self.assertEqual(result.state, RunState.NEEDS_ATTENTION)
            self.assertEqual(ledger_at_close["reserved_usd"], 0)
            self.assertEqual(ledger_at_close["calls"], [])
            synthesis_record = next(
                item for item in schedule["records"] if item["task_id"] == "T-SYNTHESIS"
            )
            self.assertTrue(any("timed out" in warning for warning in synthesis_record["warnings"]))

            transport.release_model.set()
            self.assertTrue(transport.response_returned.wait(timeout=2))
            sleep(0.05)
            self.assertEqual(registry.cost_ledger.snapshot().calls, [])
            self.assertEqual(len(transport.requests), 2)


if __name__ == "__main__":
    unittest.main()
