from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from universal_orchestrator.ingestion.archive import safe_extract_archive
from universal_orchestrator.ingestion.hardening import IngestionLimits
from universal_orchestrator.media import LocalWhisperTranscriber, TesseractOCR
from universal_orchestrator.providers.command import CommandResponse, FakeCommandTransport


class IngestionHardeningTests(unittest.TestCase):
    def test_safe_archive_extracts_regular_members_and_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "sample.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("safe/data.txt", "safe")
                archive.writestr("../escape.txt", "unsafe")
            report = safe_extract_archive(archive_path, root / "out")

            self.assertEqual(report.extracted_files, ["safe/data.txt"])
            self.assertEqual(report.rejected_members, ["../escape.txt"])
            self.assertFalse((root / "escape.txt").exists())

    def test_archive_size_limit_stops_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "sample.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("large.txt", "0123456789")
            report = safe_extract_archive(
                archive_path,
                root / "out",
                IngestionLimits(max_archive_uncompressed_bytes=5),
            )

            self.assertFalse(report.extracted_files)
            self.assertTrue(report.warnings)

    def test_ocr_adapter_is_fixtureable_and_does_not_need_network(self) -> None:
        transport = FakeCommandTransport([CommandResponse(0, "recognized text", "")])
        with tempfile.NamedTemporaryFile(suffix=".png") as image:
            ocr = TesseractOCR("tesseract", transport)
            result = ocr.extract(Path(image.name))

        self.assertEqual(result.text, "recognized text")
        self.assertNotIn("tesseract", transport.requests[0].env)

    def test_transcript_segments_preserve_timestamps(self) -> None:
        transport = FakeCommandTransport(
            [CommandResponse(0, '{"segments":[{"start":1.5,"end":3.0,"text":" hello "}]}', "")]
        )
        with tempfile.NamedTemporaryFile(suffix=".wav") as audio:
            segments = LocalWhisperTranscriber("whisper", transport).transcribe(Path(audio.name))

        self.assertEqual(segments[0].start_seconds, 1.5)
        self.assertEqual(segments[0].text, "hello")


if __name__ == "__main__":
    unittest.main()
