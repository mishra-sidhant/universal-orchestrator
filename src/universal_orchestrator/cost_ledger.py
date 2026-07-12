from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Literal

from universal_orchestrator.models import (
    BudgetStopRecord,
    CostLedgerReport,
    ProviderCallLedgerEntry,
)
from universal_orchestrator.pricing import PriceQuote, RateTable


class BudgetStopError(RuntimeError):
    def __init__(self, stop: BudgetStopRecord) -> None:
        self.stop = stop
        super().__init__(
            f"Budget stop before {stop.task_id}: estimated ${stop.estimated_usd:.6f} "
            f"exceeds remaining ${stop.remaining_usd:.6f}."
        )


@dataclass(frozen=True)
class CostAuthorization:
    call_id: str
    task_id: str
    provider_id: str
    model: str
    quote: PriceQuote
    billing_mode: Literal["metered", "subscription", "local"] = "metered"


class CostLedger:
    def __init__(self, run_id: str, ceiling_usd: float, rate_table: RateTable | None = None) -> None:
        self.run_id = run_id
        self.ceiling_usd = ceiling_usd
        self.rate_table = rate_table or RateTable.load()
        self._lock = Lock()
        self._sequence = 0
        self._reservations: dict[str, CostAuthorization] = {}
        self._calls: list[ProviderCallLedgerEntry] = []
        self._budget_stop: BudgetStopRecord | None = None

    def authorize(
        self,
        task_id: str,
        provider_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        billing_mode: Literal["metered", "subscription", "local"] = "metered",
    ) -> CostAuthorization:
        quote = self.rate_table.quote(provider_id, model, input_tokens, output_tokens)
        with self._lock:
            reserved = sum(item.quote.cost_usd for item in self._reservations.values())
            actual = sum(item.actual_usd for item in self._calls)
            remaining = max(0.0, self.ceiling_usd - actual - reserved)
            if quote.cost_usd > remaining:
                stop = BudgetStopRecord(
                    task_id=task_id,
                    provider_id=provider_id,
                    model=model,
                    estimated_usd=quote.cost_usd,
                    remaining_usd=remaining,
                    reason="Pre-call estimate exceeds the remaining run cost ceiling.",
                )
                self._budget_stop = stop
                raise BudgetStopError(stop)
            self._sequence += 1
            authorization = CostAuthorization(
                call_id=f"call_{self._sequence:04d}",
                task_id=task_id,
                provider_id=provider_id,
                model=model,
                quote=quote,
                billing_mode=billing_mode,
            )
            self._reservations[authorization.call_id] = authorization
            return authorization

    def commit(
        self,
        authorization: CostAuthorization,
        input_tokens: int,
        output_tokens: int,
    ) -> ProviderCallLedgerEntry:
        actual_quote = self.rate_table.quote(
            authorization.provider_id,
            authorization.model,
            input_tokens,
            output_tokens,
        )
        cost_status = {
            "metered": "priced",
            "subscription": "allocated_cost_unknown",
            "local": "zero_cost_local",
        }[authorization.billing_mode]
        with self._lock:
            if self._reservations.pop(authorization.call_id, None) is None:
                raise RuntimeError(f"Unknown or closed cost authorization {authorization.call_id}")
            row = ProviderCallLedgerEntry(
                call_id=authorization.call_id,
                task_id=authorization.task_id,
                provider_id=authorization.provider_id,
                model=authorization.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                estimated_usd=authorization.quote.cost_usd,
                actual_usd=actual_quote.cost_usd,
                rate_table_version=actual_quote.rate_table_version,
                rate_key=actual_quote.rate_key,
                billing_mode=authorization.billing_mode,
                cost_status=cost_status,
            )
            self._calls.append(row)
            return row

    def release(self, authorization: CostAuthorization) -> None:
        with self._lock:
            self._reservations.pop(authorization.call_id, None)

    def snapshot(self) -> CostLedgerReport:
        with self._lock:
            return CostLedgerReport(
                run_id=self.run_id,
                cost_ceiling_usd=self.ceiling_usd,
                rate_table_version=self.rate_table.version,
                rate_table_source=self.rate_table.source_path,
                calls=list(self._calls),
                total_estimated_usd=sum(item.estimated_usd for item in self._calls),
                total_actual_usd=sum(
                    item.actual_usd for item in self._calls if item.cost_status == "priced"
                ),
                unknown_cost_calls=sum(
                    item.cost_status == "allocated_cost_unknown" for item in self._calls
                ),
                reserved_usd=sum(item.quote.cost_usd for item in self._reservations.values()),
                budget_stop=self._budget_stop,
            )
