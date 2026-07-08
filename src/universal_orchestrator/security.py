from __future__ import annotations

import re

from universal_orchestrator.models import SecurityFinding


SECRET_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("openai_api_key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"), "critical"),
    ("anthropic_api_key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), "critical"),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}"), "critical"),
    ("generic_token", re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*[A-Za-z0-9_\-]{16,}"), "high"),
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
                    severity=severity,  # type: ignore[arg-type]
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

