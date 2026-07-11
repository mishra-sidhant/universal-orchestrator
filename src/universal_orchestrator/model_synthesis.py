from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import Field, ValidationError

from universal_orchestrator.models import ContextPack, ProviderTask, StrictModel, TaskNode
from universal_orchestrator.providers.base import ProviderAdapter


class ModelClaimOutput(StrictModel):
    text: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)


class ModelSynthesisOutput(StrictModel):
    summary: str = Field(min_length=1)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[ModelClaimOutput] = Field(min_length=1)


class ModelOutputValidationError(ValueError):
    pass


class CompletionLeaseExpired(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelSynthesisResult:
    output: ModelSynthesisOutput
    repaired: bool
    warnings: list[str]


class ModelSynthesisRunner:
    def run(
        self,
        adapter: ProviderAdapter,
        task: TaskNode,
        pack: ContextPack,
        operator_prompt: str,
        completion_guard=None,
    ) -> ModelSynthesisResult:
        prompt = self._initial_prompt(operator_prompt)
        first = adapter.execute(self._provider_task(task, pack, prompt, completion_guard))
        self._ensure_active(completion_guard)
        raw = str(first.output.get("summary", ""))
        try:
            parsed = self._parse(raw)
            return ModelSynthesisResult(parsed, False, self._lexical_warnings(parsed, pack))
        except ModelOutputValidationError as first_error:
            repair_prompt = self._repair_prompt(raw, first_error)
            self._ensure_active(completion_guard)
            repaired = adapter.execute(
                self._provider_task(task, pack, repair_prompt, completion_guard)
            )
            self._ensure_active(completion_guard)
            repaired_raw = str(repaired.output.get("summary", ""))
            try:
                parsed = self._parse(repaired_raw)
            except ModelOutputValidationError as second_error:
                raise ModelOutputValidationError(
                    "Model output failed schema validation after one bounded repair attempt: "
                    f"{second_error}"
                ) from second_error
            warnings = [
                "Initial model output failed validation; one bounded reformat repair succeeded.",
                *self._lexical_warnings(parsed, pack),
            ]
            return ModelSynthesisResult(parsed, True, warnings)

    def _provider_task(
        self,
        task: TaskNode,
        pack: ContextPack,
        prompt: str,
        completion_guard,
    ) -> ProviderTask:
        return ProviderTask(
            task=task,
            prompt=prompt,
            context={
                "context_pack": pack.model_dump(mode="json"),
                "completion_guard": completion_guard,
            },
            dry_run=False,
            allow_network=True,
            timeout_seconds=task.timeout_seconds,
        )

    def _ensure_active(self, completion_guard) -> None:
        if completion_guard is not None and not completion_guard.is_active():
            raise CompletionLeaseExpired("Provider response arrived after completion lease expiry.")

    def _parse(self, raw: str) -> ModelSynthesisOutput:
        try:
            payload = json.loads(raw)
            return ModelSynthesisOutput.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise ModelOutputValidationError(str(exc)) from exc

    def _initial_prompt(self, operator_prompt: str) -> str:
        return (
            f"Operator objective: {operator_prompt}\n"
            "Return only one JSON object with keys summary, findings, and claims. "
            "Each claim must have text and evidence_refs. Evidence refs may only be chunk IDs "
            "present in the supplied context. Do not add markdown fences."
        )

    def _repair_prompt(self, raw: str, error: Exception) -> str:
        return (
            "Reformat the prior response into the required JSON schema. Do not add facts or "
            "change evidence refs. Return JSON only.\n"
            f"Validation error: {error}\nPrior response: {raw}"
        )

    def _lexical_warnings(
        self,
        output: ModelSynthesisOutput,
        pack: ContextPack,
    ) -> list[str]:
        chunks = {chunk.id: chunk for chunk in pack.chunks}
        warnings: list[str] = []
        for index, claim in enumerate(output.claims):
            claim_terms = self._terms(claim.text)
            cited_terms = set().union(
                *(self._terms(chunks[ref].text) for ref in claim.evidence_refs if ref in chunks)
            )
            overlap = len(claim_terms.intersection(cited_terms)) / max(1, len(claim_terms))
            if overlap < 0.1:
                warnings.append(
                    f"Weak lexical-overlap floor: model claim {index + 1} has "
                    f"overlap={overlap:.3f}; this is not an entailment judgment."
                )
        return warnings

    def _terms(self, text: str) -> set[str]:
        return {term for term in re.findall(r"[A-Za-z0-9_]+", text.lower()) if len(term) > 2}
