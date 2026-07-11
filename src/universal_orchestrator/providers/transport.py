from __future__ import annotations

import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class HTTPRequest:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class HTTPResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes


class TransportTimeout(TimeoutError):
    """The socket-level provider deadline elapsed."""


class TransportConnectionError(ConnectionError):
    """The provider could not be reached at the network boundary."""


class HTTPTransport(Protocol):
    def send(self, request: HTTPRequest) -> HTTPResponse:
        """Send exactly one request, without provider-level retry policy."""


class UrllibHTTPTransport:
    def send(self, request: HTTPRequest) -> HTTPResponse:
        outgoing = urllib.request.Request(
            request.url,
            data=request.body,
            headers=request.headers,
            method=request.method,
        )
        try:
            with urllib.request.urlopen(outgoing, timeout=request.timeout_seconds) as response:
                return HTTPResponse(
                    status_code=response.status,
                    headers=dict(response.headers.items()),
                    body=response.read(),
                )
        except urllib.error.HTTPError as exc:
            try:
                return HTTPResponse(
                    status_code=exc.code,
                    headers=dict(exc.headers.items()) if exc.headers else {},
                    body=exc.read(),
                )
            finally:
                exc.close()
        except (socket.timeout, TimeoutError) as exc:
            raise TransportTimeout("Provider socket timed out.") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise TransportTimeout("Provider socket timed out.") from exc
            raise TransportConnectionError(f"Provider connection failed: {exc.reason}") from exc


class FakeTransport:
    """Scripted in-memory transport used by fixture tests and offline demonstrations."""

    def __init__(self, outcomes: list[HTTPResponse | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[HTTPRequest] = []

    def send(self, request: HTTPRequest) -> HTTPResponse:
        self.requests.append(request)
        if not self.outcomes:
            raise AssertionError("FakeTransport received an unexpected request.")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
