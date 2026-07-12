from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from dataclasses import dataclass
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator
from typing import Protocol

from universal_orchestrator.models import ContextChunk, RetrievalHit
from universal_orchestrator.utils import ensure_dir, sha256_bytes


class EmbeddingProvider(Protocol):
    model_id: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one normalized vector per input string."""


class HashEmbeddingProvider:
    """Deterministic local vector baseline; it is not an entailment model."""

    model_id = "local-hash-embedding-v1"

    def __init__(self, dimensions: int = 128) -> None:
        self.dimensions = max(16, dimensions)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        terms = re.findall(r"[A-Za-z0-9_]+", text.casefold())
        for term in terms:
            digest = hashlib.sha256(term.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 else -1.0
            vector[index] += sign
        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            return vector
        return [value / magnitude for value in vector]


@dataclass(frozen=True)
class _IndexedChunk:
    chunk_id: str
    content_hash: str
    text: str
    vector: list[float]


class SQLiteEmbeddingIndex:
    """Small local index with model/version-bound vectors and atomic replacement."""

    def __init__(self, path: Path | str, provider: EmbeddingProvider) -> None:
        self.path = Path(path)
        self.provider = provider
        ensure_dir(self.path.parent)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _init(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS embeddings (
                    chunk_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    vector TEXT NOT NULL,
                    PRIMARY KEY(chunk_id, model_id)
                )
                """
            )

    def upsert(self, chunks: list[ContextChunk]) -> None:
        vectors = self.provider.embed([chunk.text for chunk in chunks])
        with self._connection() as connection:
            for chunk, vector in zip(chunks, vectors, strict=True):
                connection.execute(
                    """
                    INSERT INTO embeddings(chunk_id, content_hash, model_id, text, vector)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(chunk_id, model_id) DO UPDATE SET
                        content_hash=excluded.content_hash,
                        text=excluded.text,
                        vector=excluded.vector
                    """,
                    (
                        chunk.id,
                        chunk.content_hash,
                        self.provider.model_id,
                        chunk.text,
                        ",".join(f"{value:.9g}" for value in vector),
                    ),
                )

    def search(self, query: str, limit: int = 8) -> list[tuple[str, str, list[float]]]:
        query_vector = self.provider.embed([query])[0]
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT chunk_id, text, vector FROM embeddings WHERE model_id=?",
                (self.provider.model_id,),
            ).fetchall()
        ranked = [
            (
                str(row[0]),
                str(row[1]),
                [float(value) for value in str(row[2]).split(",") if value],
            )
            for row in rows
        ]
        return sorted(
            ranked,
            key=lambda item: _cosine(query_vector, item[2]),
            reverse=True,
        )[: max(0, limit)]


class HybridRetriever:
    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self.provider = provider or HashEmbeddingProvider()

    def retrieve(self, query: str, chunks: list[ContextChunk], limit: int = 8) -> list[RetrievalHit]:
        if not chunks:
            return []
        vectors = self.provider.embed([chunk.text for chunk in chunks])
        query_vector = self.provider.embed([query])[0]
        query_terms = _terms(query)
        hits: list[RetrievalHit] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk_terms = _terms(chunk.text)
            lexical = len(query_terms.intersection(chunk_terms)) / max(1, len(query_terms))
            semantic = max(-1.0, min(1.0, _cosine(query_vector, vector)))
            combined = max(0.0, lexical * 0.65 + max(0.0, semantic) * 0.35)
            hits.append(
                RetrievalHit(
                    chunk_id=chunk.id,
                    lexical_score=min(1.0, lexical),
                    semantic_score=semantic,
                    combined_score=combined,
                    explanation="hybrid lexical plus local embedding score; not entailment",
                )
            )
        return sorted(hits, key=lambda hit: (-hit.combined_score, hit.chunk_id))[:limit]


def _terms(text: str) -> set[str]:
    return {term for term in re.findall(r"[A-Za-z0-9_]+", text.casefold()) if len(term) > 2}


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))
