from __future__ import annotations

import re
from typing import Literal

from universal_orchestrator.models import SecurityFinding


SecretSeverity = Literal["high", "critical"]


SECRET_PATTERNS: list[tuple[str, re.Pattern[str], SecretSeverity]] = [
    ("openai_api_key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"), "critical"),
    ("anthropic_api_key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), "critical"),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}"), "critical"),
    (
        "github_token",
        re.compile(r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
        "critical",
    ),
    ("google_api_key", re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b"), "critical"),
    (
        "slack_token",
        re.compile(r"\b(?:xox[baprs]-[A-Za-z0-9-]{20,}|SLACK_API_TOKEN_[A-Za-z0-9_]{8,})\b"),
        "critical",
    ),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
        "high",
    ),
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "critical",
    ),
    (
        "credential_url",
        re.compile(r"\bhttps?://[^\s:/@]+:[^@\s]+@[^\s]+", re.IGNORECASE),
        "critical",
    ),
    (
        "generic_token",
        re.compile(
            r"[\"']?(?:api[_-]?key|secret|token)[\"']?\s*[:=]\s*"
            r"[\"']?[A-Za-z0-9_./+=-]{16,}[\"']?",
            re.IGNORECASE,
        ),
        "high",
    ),
]

INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)ignore (all )?(previous|prior) instructions"),
    re.compile(r"(?i)reveal (the )?(system prompt|developer message|secrets?)"),
    re.compile(r"(?i)disable (safety|validation|security)"),
]


def scan_text(text: str, location: str | None = None) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    for kind, pattern, severity in SECRET_PATTERNS:
        for _ in pattern.finditer(text):
            findings.append(
                SecurityFinding(
                    kind=kind,
                    severity=severity,
                    message=f"Potential {kind.replace('_', ' ')} detected and redacted.",
                    location=location,
                    redacted=True,
                )
            )
    for pattern in INJECTION_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(
                SecurityFinding(
                    kind="prompt_injection_risk",
                    severity="medium",
                    message=f"Untrusted content contains instruction-like text: {match.group(0)!r}.",
                    location=location,
                    redacted=False,
                )
            )
    return findings


def redact_text(text: str) -> str:
    redacted = text
    for _, pattern, _ in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted
