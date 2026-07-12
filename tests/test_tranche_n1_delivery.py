from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from universal_orchestrator.models import HostInvocation, RunState
from universal_orchestrator.pipeline import Orchestrator


class DeliveryFinalizationTests(unittest.TestCase):
    def test_zip_validation_failure_demotes_run_and_withholds_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            orchestrator = Orchestrator(Path(directory) / "runs")
            with patch.object(
                orchestrator.artifact_builder,
                "validate_zip",
                return_value=["forced zip corruption"],
            ):
                result = orchestrator.run(HostInvocation(prompt="Produce a final report"))

            run_dir = Path(result.artifact_dir)
            zip_validation = json.loads((run_dir / "zip_validation.json").read_text())

        self.assertEqual(result.state, RunState.NEEDS_ATTENTION)
        self.assertFalse(result.quality.passed)
        self.assertEqual(zip_validation["errors"], ["forced zip corruption"])
        self.assertIsNone(result.manifest.delivery_receipt_path)
        self.assertFalse((run_dir / "delivery_receipt.json").exists())

    def test_valid_delivery_manifest_and_zip_agree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = Orchestrator(Path(directory) / "runs").run(
                HostInvocation(prompt="Produce a final report")
            )
            run_dir = Path(result.artifact_dir)
            manifest = json.loads((run_dir / "run_manifest.json").read_text())
            with zipfile.ZipFile(run_dir / "delivery_bundle.zip") as bundle:
                bundled_manifest = json.loads(bundle.read("run_manifest.json"))

        self.assertEqual(result.state, RunState.DELIVERED)
        self.assertEqual(manifest["state"], RunState.DELIVERED)
        self.assertEqual(bundled_manifest["state"], manifest["state"])
        self.assertIsNotNone(result.manifest.delivery_receipt_path)


if __name__ == "__main__":
    unittest.main()
