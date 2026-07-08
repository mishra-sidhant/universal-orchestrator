from __future__ import annotations

import re

from universal_orchestrator.models import (
    CardType,
    ContextCard,
    ContextManifest,
    ContextPack,
    InputRecord,
    InputType,
    new_id,
)
from universal_orchestrator.utils import estimate_tokens


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

