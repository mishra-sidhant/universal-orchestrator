from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from universal_orchestrator.context import ContextIntelligence
from universal_orchestrator.models import ContextChunk
from universal_orchestrator.retrieval import HashEmbeddingProvider, HybridRetriever, SQLiteEmbeddingIndex


def chunk(chunk_id: str, text: str) -> ContextChunk:
    return ContextChunk(
        id=chunk_id,
        input_id="input",
        ordinal=0,
        text=text,
        token_estimate=10,
        content_hash=f"hash-{chunk_id}",
        metadata={},
    )


class RetrievalTests(unittest.TestCase):
    def test_hybrid_retrieval_is_deterministic_and_explained(self) -> None:
        chunks = [chunk("b", "The budget ledger records token usage."), chunk("a", "The garden has green leaves.")]
        retriever = HybridRetriever(HashEmbeddingProvider(64))

        first = retriever.retrieve("token budget accounting", chunks)
        second = retriever.retrieve("token budget accounting", chunks)

        self.assertEqual([hit.chunk_id for hit in first], [hit.chunk_id for hit in second])
        self.assertEqual(first[0].chunk_id, "b")
        self.assertIn("not entailment", first[0].explanation)

    def test_embedding_index_persists_model_bound_vectors(self) -> None:
        with TemporaryDirectory() as directory:
            index = SQLiteEmbeddingIndex(f"{directory}/embeddings.sqlite3", HashEmbeddingProvider(32))
            index.upsert([chunk("a", "bounded context")])
            results = index.search("bounded context")

        self.assertEqual(results[0][0], "a")

    def test_context_packs_record_retrieval_explanations(self) -> None:
        intelligence = ContextIntelligence()
        chunks = [chunk("a", "The report discusses capacity limits."), chunk("b", "Unrelated prose.")]
        intelligence.compile_pack("T", "capacity limits", [], chunks=chunks, token_budget=100)

        self.assertTrue(intelligence.retrieval_hits_by_task["T"])
        self.assertEqual(intelligence.retrieval_hits_by_task["T"][0]["chunk_id"], "a")


if __name__ == "__main__":
    unittest.main()
