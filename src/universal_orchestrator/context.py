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
            text = record.content_text or record.summary
            if not text.strip():
                continue
            current: list[str] = []
            ordinal = 0
            start_line = 1
            current_line = 1
            marker: str | None = None
            for line_number, line in enumerate(text.splitlines() or [text], start=1):
                line_marker = self._locator_marker(line)
                if line_marker and current:
                    chunks.append(
                        self._chunk(record, ordinal, " ".join(current), start_line, current_line, marker)
                    )
                    ordinal += 1
                    current = []
                    marker = None
                for word in line.split():
                    if not current:
                        start_line = line_number
                        marker = line_marker
                    current.append(word)
                    current_line = line_number
                    if estimate_tokens(" ".join(current)) >= max_tokens:
                        chunks.append(
                            self._chunk(record, ordinal, " ".join(current), start_line, current_line, marker)
                        )
                        ordinal += 1
                        current = []
                        marker = None
            if current:
                chunks.append(
                    self._chunk(record, ordinal, " ".join(current), start_line, current_line, marker)
                )
        return chunks

    def _locator_marker(self, line: str) -> str | None:
        file_line = re.match(r"^File\s+(.+?):(\d+):", line)
        if file_line:
            return f"{file_line.group(1)} line {file_line.group(2)}"
        match = re.match(r"^(Page|Slide)\s+(\d+):", line, flags=re.IGNORECASE)
        if match:
            return f"{match.group(1).lower()} {match.group(2)}"
        sheet = re.match(r"^Sheet\s+([^:]+):", line, flags=re.IGNORECASE)
        if sheet:
            return f"sheet {sheet.group(1).strip()}"
        return None

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
                source_name=card.title,
                source_uri=str(card.metadata.get("uri", "")),
                chunk_locators={
                    chunk.id: str(chunk.metadata.get("locator", ""))
                    for chunk in chunks
                    if chunk.input_id == card.input_id
                },
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
        chunks: list[ContextChunk] | None = None,
    ) -> ContextPack:
        used_tokens = 0
        selected_chunks: list[ContextChunk] = []
        query_terms = self._terms(task)
        ranked_chunks = sorted(
            chunks or [],
            key=lambda chunk: len(query_terms.intersection(self._terms(chunk.text))),
            reverse=True,
        )
        for chunk in ranked_chunks:
            if used_tokens + chunk.token_estimate > token_budget:
                continue
            selected_chunks.append(chunk)
            used_tokens += chunk.token_estimate
        selected: list[ContextCard] = []
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
            chunks=selected_chunks,
            files_to_read=files_to_read,
            do_not_touch=[".git/", ".uo/runs/", "node_modules/", ".venv/"],
            token_budget=token_budget,
        )

    def compile_packs_for_tasks(
        self,
        task_ids: list[str],
        cards: list[ContextCard],
        token_budget: int = 16_000,
        chunks: list[ContextChunk] | None = None,
        task_queries: dict[str, str] | None = None,
    ) -> dict[str, ContextPack]:
        return {
            task_id: self.compile_pack(
                task_id,
                (task_queries or {}).get(task_id, f"Context pack for {task_id}"),
                cards,
                token_budget,
                chunks,
            )
            for task_id in task_ids
        }

    def _chunk(
        self,
        record: InputRecord,
        ordinal: int,
        text: str,
        start_line: int,
        end_line: int,
        marker: str | None,
    ) -> ContextChunk:
        file_marker = re.match(r"^(.+) line (\d+)$", marker or "")
        if file_marker:
            local_start = int(file_marker.group(2))
            local_end = local_start + (end_line - start_line)
            line_label = (
                f"line {local_start}"
                if local_start == local_end
                else f"lines {local_start}-{local_end}"
            )
            locator = f"{file_marker.group(1)} {line_label}"
        else:
            locator = marker or (
                f"line {start_line}"
                if start_line == end_line
                else f"lines {start_line}-{end_line}"
            )
        stable_source = sha256_bytes(
            f"{record.uri}:{record.content_hash or ''}".encode("utf-8")
        ).removeprefix("sha256:")[:16]
        return ContextChunk(
            id=f"chunk_{stable_source}_{ordinal}",
            input_id=record.id,
            ordinal=ordinal,
            text=text,
            token_estimate=estimate_tokens(text),
            content_hash=sha256_bytes(text.encode("utf-8")),
            metadata={
                "source_name": record.name,
                "source_uri": record.uri,
                "path": record.path,
                "locator": locator,
            },
        )

    def _card_from_record(self, record: InputRecord) -> ContextCard:
        card_type = self._card_type(record)
        metadata = dict(record.metadata)
        if record.path:
            metadata["path"] = record.path
        metadata["uri"] = record.uri
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
        return {
            term
            for term in re.findall(r"[^\W_]+(?:[_-][^\W_]+)*", text.casefold(), flags=re.UNICODE)
            if len(term) >= 2
        }
