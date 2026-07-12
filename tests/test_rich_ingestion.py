import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.media import LocalWhisperTranscriber, TesseractOCR
from universal_orchestrator.models import HostInvocation, InputAttachment, InputStatus, InputType
from universal_orchestrator.providers.command import CommandResponse, FakeCommandTransport


class RichIngestionTests(unittest.TestCase):
    def test_csv_spreadsheet_is_sampled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.csv"
            path.write_text("name,value\nalpha,1\nbeta,2\n")
            manifest = InputIngestor().ingest(
                HostInvocation(prompt="Analyze data", attachments=[InputAttachment(uri=str(path))]),
                "run_test",
            )

        record = next(item for item in manifest.inputs if item.type == InputType.SPREADSHEET)
        self.assertEqual(record.status, InputStatus.PARSED)
        self.assertEqual(record.metadata["columns"], 2)
        self.assertIn("alpha", record.summary)

    def test_image_metadata_is_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "image.png"
            Image.new("RGB", (12, 8), "white").save(path)
            manifest = InputIngestor().ingest(
                HostInvocation(prompt="Inspect image", attachments=[InputAttachment(uri=str(path))]),
                "run_test",
            )

        record = next(item for item in manifest.inputs if item.type == InputType.IMAGE)
        self.assertEqual(record.status, InputStatus.PARSED)
        self.assertEqual(record.metadata["width"], 12)
        self.assertEqual(record.metadata["height"], 8)

    def test_image_ocr_is_ingested_redacted_and_provenanced(self) -> None:
        transport = FakeCommandTransport(
            [CommandResponse(0, "Quarterly plan OPENAI_API_KEY=sk-proj-12345678901234567890", "")]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "image.png"
            Image.new("RGB", (12, 8), "white").save(path)
            manifest = InputIngestor(ocr=TesseractOCR("tesseract", transport)).ingest(
                HostInvocation(prompt="Read the image", attachments=[InputAttachment(uri=str(path))]),
                "run_test",
            )

        record = next(item for item in manifest.inputs if item.type == InputType.IMAGE)
        self.assertEqual(record.status, InputStatus.PARSED)
        self.assertEqual(record.metadata["ocr_chars"], len("Quarterly plan OPENAI_API_KEY=[REDACTED_SECRET]"))
        self.assertIn("Quarterly plan", record.content_text)
        self.assertNotIn("sk-proj-12345678901234567890", record.content_text)
        self.assertTrue(record.security_findings)
        self.assertEqual(transport.requests[0].argv[0], "tesseract")

    def test_audio_transcription_is_ingested_with_timestamps(self) -> None:
        transport = FakeCommandTransport(
            [CommandResponse(0, '{"segments":[{"start":1.5,"end":3.0,"text":"Opening remarks"}]}', "")]
        )
        transcriber = LocalWhisperTranscriber("whisper", transport)
        with tempfile.NamedTemporaryFile(suffix=".wav") as media:
            manifest = InputIngestor(transcriber=transcriber).ingest(
                HostInvocation(
                    prompt="Transcribe the recording",
                    attachments=[InputAttachment(uri=media.name)],
                ),
                "run_test",
            )

        record = next(item for item in manifest.inputs if item.type == InputType.AUDIO_VIDEO)
        self.assertEqual(record.status, InputStatus.PARSED)
        self.assertIn("[00:01.500-00:03.000] Opening remarks", record.content_text)
        self.assertEqual(record.metadata["transcript_segments"], 1)

    def test_zip_archive_is_inventoried_without_unpacking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bundle.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("safe/readme.txt", "hello")
                archive.writestr("../unsafe.txt", "bad")
            manifest = InputIngestor().ingest(
                HostInvocation(prompt="Inspect archive", attachments=[InputAttachment(uri=str(path))]),
                "run_test",
            )

        record = next(item for item in manifest.inputs if item.type == InputType.ARCHIVE)
        self.assertEqual(record.status, InputStatus.PARSED)
        self.assertEqual(record.metadata["entries"], 2)
        self.assertTrue(record.metadata["unsafe_paths"])


if __name__ == "__main__":
    unittest.main()
