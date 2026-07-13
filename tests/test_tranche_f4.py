from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
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
from universal_orchestrator.providers.transport import FakeTransport, HTTPResponse
from universal_orchestrator.routing import CapabilityRegistry


def openai_response(output_text: str, response_id: str = "resp_model") -> HTTPResponse:
    return HTTPResponse(
        200,
        {},
        json.dumps(
            {
                "id": response_id,
                "model": "fixture-model",
                "output_text": output_text,
                "usage": {"input_tokens": 30, "output_tokens": 20, "total_tokens": 50},
            }
        ).encode(),
    )


def live_invocation(source: Path, ceiling: float = 0.50) -> HostInvocation:
    return HostInvocation(
        prompt="Produce a grounded technical synthesis",
        attachments=[InputAttachment(uri=str(source))],
        user_options=UserOptions(
            allow_internet=True,
            allow_cloud=True,
            privacy_mode=PrivacyMode.CLOUD_ALLOWED,
            budget_profile="premium",
            cost_ceiling_usd=ceiling,
        ),
    )


def source_chunk_id(source: Path, invocation: HostInvocation) -> str:
    manifest = InputIngestor().ingest(invocation, "run_probe")
    chunks = ContextIntelligence().chunk_manifest(manifest)
    return next(chunk.id for chunk in chunks if chunk.input_id != "input_prompt")


def structured_output(ref: str, claim: str = "The kernel uses bounded execution evidence.") -> str:
    return json.dumps(
        {
            "summary": "Model-backed synthesis completed from the supplied source pack.",
            "findings": [
                {
                    "kind": "model_finding",
                    "severity": "info",
                    "message": claim,
                }
            ],
            "claims": [{"text": claim, "evidence_refs": [ref]}],
            "manuscript": [
                {
                    "heading": "Fixture Manuscript",
                    "objective": "Answer the supplied chapter objective.",
                    "body": claim,
                    "evidence_refs": [ref],
                }
            ],
        }
    )


class ChapterAwareTransport(FakeTransport):
    def __init__(
        self, executive_outcomes: list[HTTPResponse], retarget_valid: bool = True
    ) -> None:
        super().__init__([])
        self.executive_outcomes = list(executive_outcomes)
        self.retarget_valid = retarget_valid

    def _source_ref(self, prompt: str) -> str:
        refs = re.findall(r'"id"\s*:\s*"(chunk_[^"]+|chunk-[^"]+)"', prompt)
        if not refs:
            raise AssertionError("Model fixture did not receive a source chunk.")
        # The prompt chunk is first; use the attached source chunk for grounded fixtures.
        return refs[-1]

    def _retarget_valid_response(
        self, response: HTTPResponse, source_ref: str
    ) -> HTTPResponse:
        if not self.retarget_valid:
            return response
        try:
            envelope = json.loads(response.body.decode("utf-8"))
            output = json.loads(envelope["output_text"])
        except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
            return response
        claims = output.get("claims")
        if not isinstance(claims, list):
            return response
        for claim in claims:
            if isinstance(claim, dict) and claim.get("evidence_refs"):
                claim["evidence_refs"] = [source_ref]
        for section in output.get("manuscript", []):
            if isinstance(section, dict) and section.get("evidence_refs"):
                section["evidence_refs"] = [source_ref]
        envelope["output_text"] = json.dumps(output)
        return HTTPResponse(
            response.status_code,
            response.headers,
            json.dumps(envelope).encode("utf-8"),
        )

    def send(self, request):
        self.requests.append(request)
        if request.method == "GET":
            return HTTPResponse(200, {}, b'{"data": []}')
        body = (request.body or b"").decode("utf-8", errors="replace")
        payload = json.loads(body)
        prompt = str(payload["input"][1]["content"])
        source_ref = self._source_ref(prompt)
        if "Synthesize grounded model findings" in body:
            if not self.executive_outcomes:
                raise AssertionError("Executive synthesis made an unexpected fixture call.")
            return self._retarget_valid_response(
                self.executive_outcomes.pop(0), source_ref
            )
        return openai_response(structured_output(source_ref, "Chapter output is grounded."))


class TrancheF4ModelSynthesisTests(unittest.TestCase):
    def _run(
        self,
        root: Path,
        invocation: HostInvocation,
        outcomes: list[HTTPResponse],
        retarget_valid: bool = True,
    ):
        transport = ChapterAwareTransport(outcomes, retarget_valid=retarget_valid)
        registry = CapabilityRegistry.from_environment(
            transports={"openai.configured": transport}
        )
        result = Orchestrator(root / "runs", capability_registry=registry).run(invocation)
        return result, transport

    def test_valid_model_output_drives_synthesis_and_grounded_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
            clear=True,
        ):
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("The kernel uses bounded execution evidence for every claim.")
            invocation = live_invocation(source)
            ref = source_chunk_id(source, invocation)
            result, transport = self._run(
                root, invocation, [openai_response(structured_output(ref))]
            )
            run_dir = Path(result.artifact_dir)
            execution = json.loads((run_dir / "execution_results.json").read_text())
            synthesis = next(item for item in execution if item["task_id"] == "T-SYNTHESIS")
            audit = json.loads((run_dir / "evidence_audit.json").read_text())
            ledger = json.loads((run_dir / "cost_ledger.json").read_text())
            report = (run_dir / "final_report.md").read_text()
            manuscript = json.loads((run_dir / "manuscript.json").read_text())
            source_refs = {
                item["id"]
                for item in json.loads((run_dir / "context_chunks.json").read_text())
                if item["input_id"] != "input_prompt"
            }

        worker = synthesis["output"]["worker_output"]
        self.assertEqual(worker["synthesis_path"], "model")
        self.assertIn(worker["claims"][0]["evidence_refs"][0], source_refs)
        self.assertTrue(worker["manuscript"])
        self.assertEqual(len(manuscript["chapters"]), 3)
        self.assertIn("Fixture Manuscript", report)
        self.assertTrue(audit["passed"])
        self.assertEqual(len(ledger["calls"]), 3)
        self.assertEqual(len(transport.requests), 4)
        self.assertIn("Synthesis path: `model`", report)

    def test_malformed_output_gets_one_repair_then_extractive_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
            clear=True,
        ):
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("Trusted source passage for fallback synthesis.")
            invocation = live_invocation(source)
            result, transport = self._run(
                root,
                invocation,
                [openai_response("not-json", "resp_bad_1"), openai_response("still-not-json", "resp_bad_2")],
            )
            execution = json.loads(
                (Path(result.artifact_dir) / "execution_results.json").read_text()
            )
            synthesis = next(item for item in execution if item["task_id"] == "T-SYNTHESIS")

        worker = synthesis["output"]["worker_output"]
        self.assertEqual(worker["synthesis_path"], "extractive_fallback")
        self.assertEqual(len(transport.requests), 5)
        self.assertTrue(any("validation" in warning.lower() for warning in synthesis["warnings"]))

    def test_one_reformat_repair_can_recover_without_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
            clear=True,
        ):
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("The kernel uses bounded execution evidence for every claim.")
            invocation = live_invocation(source)
            ref = source_chunk_id(source, invocation)
            result, transport = self._run(
                root,
                invocation,
                [openai_response("not-json"), openai_response(structured_output(ref))],
            )
            execution = json.loads(
                (Path(result.artifact_dir) / "execution_results.json").read_text()
            )
            synthesis = next(item for item in execution if item["task_id"] == "T-SYNTHESIS")

        self.assertEqual(synthesis["output"]["worker_output"]["synthesis_path"], "model_repaired")
        self.assertEqual(len(transport.requests), 5)

    def test_lexical_overlap_is_labeled_warning_not_entailment_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
            clear=True,
        ):
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("Bounded execution evidence is available in this source.")
            invocation = live_invocation(source)
            ref = source_chunk_id(source, invocation)
            unrelated = "Quantum gardening predicts lunar orchestration outcomes."
            result, _ = self._run(
                root,
                invocation,
                [openai_response(structured_output(ref, unrelated))],
            )
            execution = json.loads(
                (Path(result.artifact_dir) / "execution_results.json").read_text()
            )
            synthesis = next(item for item in execution if item["task_id"] == "T-SYNTHESIS")
            audit = json.loads(
                (Path(result.artifact_dir) / "evidence_audit.json").read_text()
            )

        self.assertTrue(audit["claims"][0]["resolved"])
        self.assertTrue(any("not an entailment" in warning for warning in synthesis["warnings"]))

    def test_fabricated_model_ref_is_unsupported_and_fails_evidence_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
            clear=True,
        ):
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("Grounded source evidence exists here.")
            invocation = live_invocation(source)
            ref = source_chunk_id(source, invocation)
            fabricated_output = json.loads(structured_output("chunk_fabricated"))
            fabricated_output["manuscript"][0]["evidence_refs"] = [ref]
            result, _ = self._run(
                root,
                invocation,
                [openai_response(json.dumps(fabricated_output))],
                retarget_valid=False,
            )
            audit = json.loads(
                (Path(result.artifact_dir) / "evidence_audit.json").read_text()
            )

        self.assertFalse(audit["passed"])
        self.assertIn("chunk_fabricated", audit["invalid_evidence_refs"])
        self.assertTrue(any(not claim["resolved"] for claim in audit["claims"]))
        self.assertEqual(result.state, RunState.NEEDS_ATTENTION)

    def test_budget_stop_is_terminal_needs_attention_before_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
            clear=True,
        ):
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("Source evidence that must not trigger an unaffordable call.")
            invocation = live_invocation(source, ceiling=0.000001)
            result, transport = self._run(root, invocation, [openai_response("unused")])
            run_dir = Path(result.artifact_dir)
            ledger = json.loads((run_dir / "cost_ledger.json").read_text())
            budget = json.loads((run_dir / "budget_report.json").read_text())

        self.assertEqual(
            [request for request in transport.requests if request.url.endswith("/responses")],
            [],
        )
        self.assertEqual(result.state, RunState.NEEDS_ATTENTION)
        self.assertIsNotNone(ledger["budget_stop"])
        self.assertIn(
            ledger["budget_stop"]["task_id"],
            {"T-SYNTHESIS", "T-CHAPTER-002", "T-CHAPTER-003"},
        )
        self.assertEqual(budget["budget_stop"], ledger["budget_stop"])

    def test_without_provider_configuration_extractive_path_remains_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {}, clear=True):
            result = Orchestrator(Path(tmp) / "runs").run(
                HostInvocation(prompt="Build a keyless local report")
            )
            execution = json.loads(
                (Path(result.artifact_dir) / "execution_results.json").read_text()
            )
            synthesis = next(item for item in execution if item["task_id"] == "T-SYNTHESIS")

        self.assertEqual(synthesis["output"]["worker_output"]["synthesis_path"], "extractive")


if __name__ == "__main__":
    unittest.main()
