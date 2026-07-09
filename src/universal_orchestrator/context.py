from __future__ import annotations

import re
from collections import defaultdict

from universal_orchestrator.models import (
    CardType,
    ContextCard,
    ContextChunk,
    ContextManifest,
    ContextPack,
    InputRecord,
    InputType,
    ProvenanceRecord,
    new_id,
)
from universal_orchestrator.utils import estimate_tokens, sha256_bytes


class ContextIntelligence:
    def build_cards(self, manifest: ContextManifest) -> list[ContextCard]:
        cards: list[ContextCard] = []
        for record in manifest.inputs:
            cards.append(self._card_from_record(record))
            for finding in record.security_findings:
                cards.append(
                    ContextCard(
                        id=new_id("card"),
                        input_id=record.id,
                        card_type=CardType.RISK,
                        title=f"Security finding: {finding.kind}",
                        summary=finding.message,
                        excerpts=[],
                        metadata=finding.model_dump(mode="json"),
                        trust_level="runtime",
                        token_estimate=estimate_tokens(finding.message),
                    )
                )
        return cards

    def rank_cards(self, prompt: str, cards: list[ContextCard]) -> list[ContextCard]:
        prompt_terms = self._terms(prompt)
        ranked: list[ContextCard] = []
        for card in cards:
            haystack = f"{card.title} {card.summary} {' '.join(card.excerpts)}"
            card_terms = self._terms(haystack)
            overlap = len(prompt_terms.intersection(card_terms))
            specificity = min(1.0, len(card_terms) / 80)
            risk_boost = 0.15 if card.card_type == CardType.RISK else 0.0
            relevance = min(1.0, (overlap / max(1, len(prompt_terms))) + specificity * 0.2 + risk_boost)
            ranked.append(card.model_copy(update={"relevance_score": round(relevance, 4)}))
        return sorted(ranked, key=lambda item: item.relevance_score, reverse=True)

    def build_index(self, cards: list[ContextCard]) -> dict[str, list[str]]:
        index: dict[str, list[str]] = defaultdict(list)
        for card in cards:
            text = f"{card.title} {card.summary} {' '.join(card.excerpts)}"
            for term in self._terms(text):
                index[term].append(card.id)
        return dict(index)

    def chunk_manifest(self, manifest: ContextManifest, max_tokens: int = 220) -> list[ContextChunk]:
        chunks: list[ContextChunk] = []
        for record in manifest.inputs:
            words = record.summary.split()
            if not words:
                continue
            current: list[str] = []
            ordinal = 0
            for word in words:
                current.append(word)
                if estimate_tokens(" ".join(current)) >= max_tokens:
                    chunks.append(self._chunk(record.id, ordinal, " ".join(current)))
                    ordinal += 1
                    current = []
            if current:
                chunks.append(self._chunk(record.id, ordinal, " ".join(current)))
        return chunks

    def provenance(self, cards: list[ContextCard], chunks: list[ContextChunk]) -> list[ProvenanceRecord]:
        chunks_by_input: dict[str, list[str]] = defaultdict(list)
        hashes_by_input: dict[str, str] = {}
        for chunk in chunks:
            chunks_by_input[chunk.input_id].append(chunk.id)
            hashes_by_input.setdefault(chunk.input_id, chunk.content_hash)
        return [
            ProvenanceRecord(
                source_id=card.input_id,
                card_id=card.id,
                chunk_ids=chunks_by_input.get(card.input_id, []),
                trust_level=card.trust_level,
                content_hash=hashes_by_input.get(card.input_id),
            )
            for card in cards
        ]

    def deduplicate_cards(self, cards: list[ContextCard]) -> list[ContextCard]:
        seen: set[str] = set()
        deduped: list[ContextCard] = []
        for card in cards:
            key = sha256_bytes(f"{card.title}:{card.summary}".lower().encode("utf-8"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(card)
        return deduped

    def retrieve(self, query: str, cards: list[ContextCard], limit: int = 8) -> list[ContextCard]:
        ranked = self.rank_cards(query, cards)
        return ranked[:limit]

    def detect_conflicts(self, cards: list[ContextCard]) -> list[str]:
        conflicts: list[str] = []
        summaries_by_title: dict[str, set[str]] = defaultdict(set)
        for card in cards:
            summaries_by_title[card.title.lower()].add(card.summary.lower())
            lowered = card.summary.lower()
            if any(marker in lowered for marker in ["contradicts", "conflicts with", "inconsistent with"]):
                conflicts.append(f"Potential conflict marker in {card.title}")
        for title, summaries in summaries_by_title.items():
            if len(summaries) > 1:
                conflicts.append(f"Multiple differing summaries for {title}")
        return sorted(set(conflicts))

    def compile_pack(
        self,
        task_id: str,
        task: str,
        cards: list[ContextCard],
        token_budget: int = 16_000,
    ) -> ContextPack:
        selected: list[ContextCard] = []
        used_tokens = 0
        for card in cards:
            if used_tokens + card.token_estimate > token_budget:
                continue
            selected.append(card)
            used_tokens += card.token_estimate
        files_to_read = [
            str(card.metadata["path"])
            for card in selected
            if isinstance(card.metadata.get("path"), str)
        ]
        return ContextPack(
            task_id=task_id,
            task=task,
            cards=selected,
            files_to_read=files_to_read,
            do_not_touch=[".git/", ".uo/runs/", "node_modules/", ".venv/"],
            token_budget=token_budget,
        )

    def compile_packs_for_tasks(
        self,
        task_ids: list[str],
        cards: list[ContextCard],
        token_budget: int = 16_000,
    ) -> dict[str, ContextPack]:
        return {
            task_id: self.compile_pack(task_id, f"Context pack for {task_id}", cards, token_budget)
            for task_id in task_ids
        }

    def _chunk(self, input_id: str, ordinal: int, text: str) -> ContextChunk:
        return ContextChunk(
            id=f"chunk_{input_id}_{ordinal}",
            input_id=input_id,
            ordinal=ordinal,
            text=text,
            token_estimate=estimate_tokens(text),
            content_hash=sha256_bytes(text.encode("utf-8")),
        )

    def _card_from_record(self, record: InputRecord) -> ContextCard:
        card_type = self._card_type(record)
        metadata = dict(record.metadata)
        if record.path:
            metadata["path"] = record.path
        summary = record.summary or f"{record.type} input named {record.name}."
        return ContextCard(
            id=new_id("card"),
            input_id=record.id,
            card_type=card_type,
            title=record.name,
            summary=summary,
            excerpts=[summary] if summary else [],
            metadata=metadata,
            trust_level="user" if record.type == InputType.PROMPT else "source",
            token_estimate=estimate_tokens(summary),
        )

    def _card_type(self, record: InputRecord) -> CardType:
        if record.type == InputType.REPO:
            return CardType.REPO
        if record.type == InputType.IMAGE:
            return CardType.VISUAL
        if record.type in {InputType.SPREADSHEET, InputType.API}:
            return CardType.DATA if record.type == InputType.SPREADSHEET else CardType.API
        return CardType.SOURCE

    def _terms(self, text: str) -> set[str]:
        return {term for term in re.findall(r"[a-zA-Z0-9_]{3,}", text.lower())}
