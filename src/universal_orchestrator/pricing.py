from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PriceQuote:
    provider_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    rate_table_version: str
    rate_key: str


class RateTable:
    def __init__(self, payload: dict[str, Any], source_path: str) -> None:
        self.payload = payload
        self.source_path = source_path
        self.version = str(payload["version"])
        self.unit_tokens = int(payload.get("unit_tokens", 1_000_000))

    @classmethod
    def load(cls, path: Path | str | None = None) -> "RateTable":
        if path is None:
            resource = files("universal_orchestrator").joinpath("provider_rates.json")
            return cls(json.loads(resource.read_text()), str(resource))
        source = Path(path)
        return cls(json.loads(source.read_text()), str(source))

    def quote(
        self,
        provider_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> PriceQuote:
        provider = self.payload.get("providers", {}).get(provider_id)
        if not isinstance(provider, dict):
            raise KeyError(f"No configured rates for provider {provider_id}")
        models = provider.get("models", {})
        has_model_rate = isinstance(models, dict) and model in models
        rate_key = model if has_model_rate else "default"
        rates = models[model] if has_model_rate else provider.get("default")
        if not isinstance(rates, dict):
            raise KeyError(f"No configured rates for {provider_id}/{model}")
        unit = Decimal(self.unit_tokens)
        input_cost = Decimal(max(0, input_tokens)) * Decimal(str(rates["input_usd"])) / unit
        output_cost = Decimal(max(0, output_tokens)) * Decimal(str(rates["output_usd"])) / unit
        return PriceQuote(
            provider_id=provider_id,
            model=model,
            input_tokens=max(0, input_tokens),
            output_tokens=max(0, output_tokens),
            cost_usd=float(input_cost + output_cost),
            rate_table_version=self.version,
            rate_key=rate_key,
        )
