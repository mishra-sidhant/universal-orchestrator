from __future__ import annotations

import io
import json
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from time import sleep
from unittest.mock import patch

from pypdf import PdfReader

import universal_orchestrator.cache as cache_module
from universal_orchestrator.artifact_builders import ArtifactBuilder
from universal_orchestrator.artifacts import ArtifactStore
from universal_orchestrator.context import ContextIntelligence
from universal_orchestrator.contracts import ProductContractCompiler
from universal_orchestrator.execution import DeterministicExecutor
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.models import (
    ContextCard,
    ContextChunk,
    ContextPack,
    CostTier,
    HostInvocation,
    InputAttachment,
    ProviderDescriptor,
    ProviderHealth,
    ProviderKind,
    ProviderStatus,
    ProviderTask,
    RoutingAction,
    RoutingDecision,
    TaskNode,
    TaskType,
    new_id,
)
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.providers.base import JSONHTTPMixin, ProviderAdapterRegistry
from universal_orchestrator.providers.openai import OpenAIResponsesAdapter
from universal_orchestrator.routing import CapabilityRegistry
from universal_orchestrator.utils import write_json


class TrancheE5InputRealityTests(unittest.TestCase):
    def test_repo_source_body_reaches_chunk_and_final_citation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            (repo / ".git").mkdir(parents=True)
            (repo / "src").mkdir()
            source = repo / "src" / "payment_engine.py"
            source.write_text(
                "def reconcile_payment():\n"
                "    return 'PAYMENT_RECONCILIATION_SENTINEL'\n"
            )
            result = Orchestrator(root / "runs").run(
                HostInvocation(
                    prompt="Build a serious technical report about payment reconciliation",
                    attachments=[InputAttachment(uri=str(repo))],
                )
            )

            chunks = json.loads((Path(result.artifact_dir) / "context_chunks.json").read_text())
            matching = [
                chunk for chunk in chunks if "PAYMENT_RECONCILIATION_SENTINEL" in chunk["text"]
            ]
            self.assertTrue(matching)
            self.assertIn("src/payment_engine.py", matching[0]["metadata"]["locator"])
            report = (Path(result.artifact_dir) / "final_report.md").read_text()
            self.assertIn("src/payment_engine.py", report)
            self.assertIn(f"[{matching[0]['id']}]", report)

    def test_explicit_report_intent_beats_repo_presence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            (repo / ".git").mkdir(parents=True)
            pdf = root / "design.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            invocation = HostInvocation(
                prompt="Use these PDFs and this repo to build a serious technical report",
                attachments=[InputAttachment(uri=str(pdf)), InputAttachment(uri=str(repo))],
            )
            manifest = InputIngestor().ingest(invocation, "run_contract")

            contract = ProductContractCompiler().compile(invocation, manifest)

        self.assertEqual(contract.run_type, "research_report")

    def test_unicode_terms_rank_and_retrieve_hindi_content(self) -> None:
        context = ContextIntelligence()
        card = ContextCard(
            id="card_hindi",
            input_id="input_hindi",
            card_type="source",
            title="स्रोत",
            summary="भुगतान समाधान और ग्राहक अनुभव",
        )
        irrelevant = ContextChunk(
            id="chunk_irrelevant",
            input_id="input_other",
            ordinal=0,
            text="completely unrelated text",
            token_estimate=8,
            content_hash="sha256:other",
        )
        chunk = ContextChunk(
            id="chunk_hindi",
            input_id="input_hindi",
            ordinal=0,
            text="भुगतान समाधान विश्वसनीय है",
            token_estimate=8,
            content_hash="sha256:test",
        )

        ranked = context.rank_cards("भुगतान समाधान", [card])
        pack = context.compile_pack(
            "T-HINDI",
            "भुगतान समाधान",
            ranked,
            token_budget=8,
            chunks=[irrelevant, chunk],
        )

        self.assertGreater(ranked[0].relevance_score, 0)
        self.assertEqual(pack.chunks[0].id, "chunk_hindi")

    def test_context_pack_enters_all_provider_dry_run_payloads(self) -> None:
        registry = CapabilityRegistry.from_environment().adapter_registry()
        task = TaskNode(id="T", run_id="R", title="Synthesize", task_type=TaskType.FINAL_SYNTHESIS)
        pack = ContextPack(
            task_id=task.id,
            task="Synthesize",
            chunks=[
                ContextChunk(
                    id="chunk_real",
                    input_id="input_real",
                    ordinal=0,
                    text="CONTEXT_PACK_SENTINEL",
                    token_estimate=6,
                    content_hash="sha256:real",
                    metadata={"locator": "src/kernel.py lines 4-8"},
                ),
                ContextChunk(
                    id="chunk_overflow",
                    input_id="input_real",
                    ordinal=1,
                    text="OVERFLOW_CONTEXT_MUST_NOT_ENTER_PAYLOAD",
                    token_estimate=6,
                    content_hash="sha256:overflow",
                ),
            ],
            token_budget=6,
        )
        provider_task = ProviderTask(
            task=task,
            prompt="Use the supplied context",
            context={"context_pack": pack.model_dump(mode="json")},
            dry_run=True,
        )

        for provider_id in ("openai.configured", "anthropic.configured", "ollama.local"):
            with self.subTest(provider=provider_id):
                result = registry.require(provider_id).execute(provider_task)
                preview = json.dumps(result.output["request_preview"])
                self.assertIn("CONTEXT_PACK_SENTINEL", preview)
                self.assertNotIn("OVERFLOW_CONTEXT_MUST_NOT_ENTER_PAYLOAD", preview)
                self.assertIsNotNone(result.cost_estimate)
                self.assertTrue(result.output["usage"]["estimated"])

    def test_pipeline_budget_report_contains_reconciled_usage_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = Orchestrator(Path(tmp) / "runs").run(
                HostInvocation(prompt="Produce a final technical report")
            )
            budget = json.loads((Path(result.artifact_dir) / "budget_report.json").read_text())

        ledger = budget["usage_ledger"]
        self.assertEqual(len(ledger), len(budget["task_budgets"]))
        self.assertEqual(
            sum(item["total_tokens"] for item in ledger),
            budget["total_estimated_tokens"],
        )
        self.assertTrue(budget["usage_reconciled"])
        self.assertTrue(all(item["estimated"] for item in ledger))

    def test_anthropic_max_tokens_is_configurable(self) -> None:
        adapter = CapabilityRegistry.from_environment().adapter_registry().require(
            "anthropic.configured"
        )
        task = ProviderTask(
            task=TaskNode(id="T", run_id="R", title="Write", task_type=TaskType.FINAL_SYNTHESIS),
            prompt="Write",
        )
        with patch.dict("os.environ", {"ANTHROPIC_MAX_TOKENS": "8192"}):
            result = adapter.execute(task)

        self.assertEqual(result.output["request_preview"]["max_tokens"], 8192)
        self.assertEqual(result.cost_estimate.output_tokens, 8192)

    def test_http_provider_retries_429_and_5xx(self) -> None:
        mixin = JSONHTTPMixin()
        retryable = urllib.error.HTTPError(
            "https://provider.test",
            429,
            "limited",
            {},
            io.BytesIO(b"limited"),
        )
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok": true}'
        with patch(
            "universal_orchestrator.providers.base.urllib.request.urlopen",
            side_effect=[retryable, response],
        ) as urlopen, patch(
            "universal_orchestrator.providers.base.sleep", create=True
        ) as backoff:
            payload = mixin._post_json(
                "https://provider.test", {}, {}, 5, max_attempts=3, backoff_seconds=0.01
            )

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(urlopen.call_count, 2)
        backoff.assert_called_once_with(0.01)

    def test_ids_remain_unique_when_time_is_frozen(self) -> None:
        frozen = datetime(2026, 7, 11, tzinfo=timezone.utc)
        with patch("universal_orchestrator.models.utc_now", return_value=frozen):
            ids = {new_id("run") for _ in range(500)}

        self.assertEqual(len(ids), 500)

    def test_json_write_is_atomic_and_preserves_previous_file_on_replace_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifact.json"
            write_json(path, {"version": 1})
            with patch("universal_orchestrator.utils.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    write_json(path, {"version": 2})

            self.assertEqual(json.loads(path.read_text()), {"version": 1})
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_exact_cache_name_and_dead_renderers_are_removed(self) -> None:
        self.assertTrue(hasattr(cache_module, "ExactMatchCache"))
        self.assertFalse(hasattr(cache_module, "SemanticCache"))
        self.assertFalse(hasattr(ArtifactStore, "write_final_report"))
        self.assertFalse(hasattr(ArtifactStore, "_render_report"))
        self.assertFalse(hasattr(DeterministicExecutor, "_summary"))

    def test_execution_result_has_measured_provider_duration(self) -> None:
        class SlowAdapter(OpenAIResponsesAdapter):
            def execute(self, task):
                sleep(0.01)
                return super().execute(task)

        descriptor = ProviderDescriptor(
            id="slow.test",
            kind=ProviderKind.HOSTED_MODEL,
            enabled=True,
            capabilities={"final_synthesis": 1.0},
            cost_tier=CostTier.FREE,
            health=ProviderHealth(status=ProviderStatus.HEALTHY, reliability_score=1.0),
        )
        task = TaskNode(id="T", run_id="R", title="Write", task_type=TaskType.FINAL_SYNTHESIS)
        result = DeterministicExecutor(
            adapters=ProviderAdapterRegistry([SlowAdapter(descriptor)]),
            dry_run_external=True,
        ).execute(
            [task],
            [
                RoutingDecision(
                    task_id=task.id,
                    action=RoutingAction.ROUTE,
                    provider_id="slow.test",
                    reason="test",
                )
            ],
        )[0]

        self.assertGreaterEqual((result.completed_at - result.started_at).total_seconds(), 0.01)

    def test_pdf_builder_escapes_markup_and_renders_h2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "safe.pdf"
            ArtifactBuilder().build_pdf(
                "# Report\n\n## Findings\n\nFilename <x>.md & evidence are preserved.",
                path,
            )
            text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)

        self.assertIn("Findings", text)
        self.assertIn("<x>.md & evidence", text)


if __name__ == "__main__":
    unittest.main()
