class UniversalOrchestratorError(Exception):
    """Base exception for orchestrator failures."""


class IngestionError(UniversalOrchestratorError):
    """Raised when an input cannot be safely ingested."""


class DAGValidationError(UniversalOrchestratorError):
    """Raised when a task DAG is invalid."""


class ArtifactError(UniversalOrchestratorError):
    """Raised when artifact creation or validation fails."""


class RunCancelledError(UniversalOrchestratorError):
    """Raised when a durable cancellation request stops an active run."""
