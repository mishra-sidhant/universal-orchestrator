from __future__ import annotations

import shutil
import json
from dataclasses import dataclass
from pathlib import Path

from universal_orchestrator.providers.command import (
    CommandRequest,
    CommandResponse,
    CommandTransport,
    SubprocessCommandTransport,
    sanitized_cli_environment,
)


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float | None
    warning: str | None = None


@dataclass(frozen=True)
class TranscriptSegment:
    start_seconds: float
    end_seconds: float
    text: str


class TesseractOCR:
    def __init__(self, executable: str | None = None, transport: CommandTransport | None = None) -> None:
        self.executable = executable or shutil.which("tesseract")
        self.transport = transport or SubprocessCommandTransport()

    @property
    def available(self) -> bool:
        return self.executable is not None

    def extract(self, path: Path, timeout_seconds: float = 30.0) -> OCRResult:
        if not self.executable:
            return OCRResult("", None, "Tesseract is not installed; OCR was not attempted.")
        response = self.transport.run(
            CommandRequest(
                argv=(self.executable, str(path), "stdout", "--dpi", "300"),
                stdin="",
                timeout_seconds=timeout_seconds,
                env=sanitized_cli_environment(),
            )
        )
        if response.returncode != 0:
            return OCRResult("", None, "Tesseract returned a non-zero exit code.")
        return OCRResult(response.stdout.strip(), None)


class MediaTooling:
    """Capability probe for optional media tools; it never downloads models."""

    def __init__(self) -> None:
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")
        self.tesseract = shutil.which("tesseract")
        self.whisper = shutil.which("whisper")

    def readiness(self) -> dict[str, bool]:
        return {
            "ffmpeg": self.ffmpeg is not None,
            "ffprobe": self.ffprobe is not None,
            "tesseract": self.tesseract is not None,
            "whisper": self.whisper is not None,
            "transcription_model_download": False,
        }


class LocalWhisperTranscriber:
    """Optional local Whisper CLI boundary; model acquisition is operator-managed."""

    def __init__(self, executable: str | None = None, transport: CommandTransport | None = None) -> None:
        self.executable = executable or shutil.which("whisper")
        self.transport = transport or SubprocessCommandTransport()

    @property
    def available(self) -> bool:
        return self.executable is not None

    def transcribe(self, path: Path, timeout_seconds: float = 300.0) -> list[TranscriptSegment]:
        if not self.executable:
            return []
        response = self.transport.run(
            CommandRequest(
                argv=(self.executable, str(path), "--output_format", "json", "--stdout"),
                stdin="",
                timeout_seconds=timeout_seconds,
                env=sanitized_cli_environment(),
            )
        )
        if response.returncode != 0:
            return []
        try:
            payload = json.loads(response.stdout)
        except json.JSONDecodeError:
            return []
        segments = payload.get("segments") if isinstance(payload, dict) else None
        if not isinstance(segments, list):
            return []
        return [
            TranscriptSegment(float(item.get("start", 0.0)), float(item.get("end", 0.0)), str(item.get("text", "")).strip())
            for item in segments
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ]
