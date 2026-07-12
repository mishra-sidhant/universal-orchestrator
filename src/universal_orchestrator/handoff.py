from __future__ import annotations

from universal_orchestrator.capacity import CapacityBroker
from universal_orchestrator.models import HandoffRecord
from universal_orchestrator.runtime import RuntimeStore


class HandoffController:
    """Selects a new connector for the same task without replaying a failed connector."""

    def __init__(
        self,
        capacity: CapacityBroker,
        runtime: RuntimeStore | None = None,
        max_attempts: int = 3,
        max_handoffs: int = 2,
    ) -> None:
        self.capacity = capacity
        self.runtime = runtime
        self.max_attempts = max(1, max_attempts)
        self.max_handoffs = max(0, max_handoffs)

    def choose(
        self,
        run_id: str,
        task_id: str,
        attempt: int,
        candidates: list[str],
        attempted_connectors: set[str],
        reason: str,
        current_connector_id: str | None = None,
        checkpoint_sequence: int | None = None,
    ) -> HandoffRecord | None:
        existing = self.runtime.handoffs(run_id, task_id) if self.runtime is not None else []
        if attempt >= self.max_attempts or len(existing) >= self.max_handoffs:
            return None
        available = [
            connector_id
            for connector_id in candidates
            if connector_id not in attempted_connectors
            and connector_id != current_connector_id
            and self.capacity.is_eligible(connector_id)
        ]
        if not available:
            return None
        target = sorted(available, key=lambda item: (-self.capacity.score(item), item))[0]
        handoff = HandoffRecord(
            run_id=run_id,
            task_id=task_id,
            attempt=attempt + 1,
            from_connector_id=current_connector_id,
            to_connector_id=target,
            reason=reason,
            preserved_checkpoint_sequence=checkpoint_sequence,
        )
        if self.runtime is not None:
            self.runtime.save_handoff(handoff)
        return handoff
