from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    stamp = utc_now().strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}_{stamp}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class Host(StrEnum):
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"
    CURSOR = "cursor"
    VSCODE_COPILOT = "vscode_copilot"
    WINDSURF = "windsurf"
    TERMINAL = "terminal"
    API = "api"
    CI = "ci"


class QualityLevel(StrEnum):
    FAST = "fast"
    STANDARD = "standard"
    SERIOUS = "serious"
    MAX = "max"


class BudgetProfile(StrEnum):
    CHEAP = "cheap"
    BALANCED = "balanced"
    PREMIUM = "premium"
    UNLIMITED = "unlimited"


class PrivacyMode(StrEnum):
    LOCAL_ONLY = "local_only"
    BALANCED = "balanced"
    CLOUD_ALLOWED = "cloud_allowed"
    EXPLICIT_APPROVAL = "explicit_approval"


class RunState(StrEnum):
    RECEIVED = "received"
    INGESTING = "ingesting"
    CONTEXT_INDEXING = "context_indexing"
    CONTRACTING = "contracting"
    PLANNING = "planning"
    PLAN_REVIEW = "plan_review"
    ROUTING = "routing"
    EXECUTING = "executing"
    AGGREGATING = "aggregating"
    GAP_ANALYSIS = "gap_analysis"
    REPAIR_EXECUTION = "repair_execution"
    FINAL_ASSEMBLY = "final_assembly"
    VALIDATION = "validation"
    ARTIFACT_BUILD = "artifact_build"
    ARTIFACT_VALIDATION = "artifact_validation"
    PACKAGING = "packaging"
    DELIVERED = "delivered"
    FAILED = "failed"


class InputType(StrEnum):
    PROMPT = "prompt"
    TEXT = "text"
    MARKDOWN = "markdown"
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    SPREADSHEET = "spreadsheet"
    IMAGE = "image"
    FOLDER = "folder"
    REPO = "repo"
    URL = "url"
    API = "api"
    ARCHIVE = "archive"
    AUDIO_VIDEO = "audio_video"
    CODE = "code"
    UNKNOWN = "unknown"


class InputStatus(StrEnum):
    PENDING = "pending"
    PARSED = "parsed"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    FAILED = "failed"


class CardType(StrEnum):
    SOURCE = "source"
    EVIDENCE = "evidence"
    REPO = "repo"
    VISUAL = "visual"
    DATA = "data"
    API = "api"
    RISK = "risk"


class TaskType(StrEnum):
    INGESTION = "ingestion"
    RESEARCH = "research"
    SUMMARIZATION = "summarization"
    CODE_EDIT = "code_edit"
    CODE_REVIEW = "code_review"
    ARTIFACT_BUILD = "artifact_build"
    VALIDATION = "validation"
    FINAL_SYNTHESIS = "final_synthesis"
    ROUTING = "routing"
    PLANNING = "planning"
    QUALITY_REPAIR = "quality_repair"


class Criticality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MISSION_CRITICAL = "mission_critical"


class CostTier(StrEnum):
    FREE = "free"
    CHEAP = "cheap"
    MEDIUM = "medium"
    PREMIUM = "premium"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CACHED = "cached"
    WAITING_FOR_USER = "waiting_for_user"


class RoutingAction(StrEnum):
    ROUTE = "route"
    ROUTE_DEGRADED = "route_degraded"
    RESHAPE = "reshape"
    PAUSE = "pause"


class ProviderKind(StrEnum):
    HOSTED_MODEL = "hosted_model"
    LOCAL_MODEL = "local_model"
    DETERMINISTIC_TOOL = "deterministic_tool"
    HOST_AGENT = "host_agent"


class ProviderStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class ArtifactType(StrEnum):
    MANIFEST = "manifest"
    REPORT = "report"
    JSON = "json"
    PATCH = "patch"
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    IMAGE = "image"
    ZIP = "zip"
    DEBUG_BUNDLE = "debug_bundle"


class UserOptions(StrictModel):
    quality: QualityLevel = QualityLevel.SERIOUS
    budget_profile: BudgetProfile = BudgetProfile.BALANCED
    artifact_types: list[str] = Field(default_factory=list)
    allow_internet: bool = False
    allow_repo_writes: bool = False
    allow_shell: bool = False
    privacy_mode: PrivacyMode = PrivacyMode.BALANCED


class InputAttachment(StrictModel):
    uri: str
    name: str | None = None
    media_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HostInvocation(StrictModel):
    id: str = Field(default_factory=lambda: new_id("inv"))
    host: Host = Host.TERMINAL
    command: str = "run"
    prompt: str
    cwd: str | None = None
    attachments: list[InputAttachment] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    selected_text: str | None = None
    open_files: list[str] = Field(default_factory=list)
    user_options: UserOptions = Field(default_factory=UserOptions)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be empty")
        return value


class SecurityFinding(StrictModel):
    kind: str
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    location: str | None = None
    redacted: bool = False


class InputRecord(StrictModel):
    id: str
    type: InputType
    name: str
    uri: str
    path: str | None = None
    status: InputStatus
    content_hash: str | None = None
    size_bytes: int | None = None
    mime_type: str | None = None
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    security_findings: list[SecurityFinding] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ContextManifest(StrictModel):
    run_id: str
    invocation_id: str
    prompt: dict[str, Any]
    inputs: list[InputRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def parsed_count(self) -> int:
        return len([item for item in self.inputs if item.status == InputStatus.PARSED])


class ContextCard(StrictModel):
    id: str
    input_id: str
    card_type: CardType
    title: str
    summary: str
    excerpts: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    trust_level: Literal["runtime", "user", "local_project", "source", "web", "model"] = "source"
    token_estimate: int = 0
    relevance_score: float = 0.0


class ContextPack(StrictModel):
    task_id: str
    task: str
    cards: list[ContextCard] = Field(default_factory=list)
    files_to_read: list[str] = Field(default_factory=list)
    do_not_touch: list[str] = Field(default_factory=list)
    token_budget: int = 16_000


class DefinitionOfDone(StrictModel):
    gates: list[str]
    artifact_checks: list[str] = Field(default_factory=list)
    validation_checks: list[str] = Field(default_factory=list)
    final_response_rules: list[str] = Field(default_factory=list)


class ProductContract(StrictModel):
    id: str = Field(default_factory=lambda: new_id("contract"))
    run_type: str
    requested_output: str
    primary_artifacts: list[str]
    secondary_artifacts: list[str] = Field(default_factory=list)
    audience: str = "serious general user"
    quality_bar: str = "serious"
    must_have: list[str]
    must_not_have: list[str]
    definition_of_done: DefinitionOfDone
    constraints: dict[str, Any] = Field(default_factory=dict)


class PlanCandidate(StrictModel):
    role: str
    bias: str
    proposed_task_ids: list[str]
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    score: float = Field(default=0.0, ge=0.0, le=1.0)


class PlanReview(StrictModel):
    run_id: str
    candidates: list[PlanCandidate]
    selected_task_ids: list[str]
    merged_strengths: list[str] = Field(default_factory=list)
    residual_risks: list[str] = Field(default_factory=list)
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    critical_path: list[str] = Field(default_factory=list)
    estimated_cost_tier: CostTier = CostTier.FREE
    simulation: dict[str, Any] = Field(default_factory=dict)


class ContextChunk(StrictModel):
    id: str
    input_id: str
    ordinal: int
    text: str
    token_estimate: int
    content_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProvenanceRecord(StrictModel):
    source_id: str
    card_id: str
    chunk_ids: list[str] = Field(default_factory=list)
    trust_level: str
    content_hash: str | None = None


class RepoMap(StrictModel):
    root: str
    frameworks: list[str] = Field(default_factory=list)
    languages: dict[str, int] = Field(default_factory=dict)
    test_commands: list[str] = Field(default_factory=list)
    package_files: list[str] = Field(default_factory=list)
    hot_files: list[str] = Field(default_factory=list)
    generated_or_dependency_dirs: list[str] = Field(default_factory=list)


class RetryPolicy(StrictModel):
    max_attempts: int = 1
    backoff_seconds: float = 0.0


class FallbackPolicy(StrictModel):
    allow_provider_fallback: bool = True
    allow_task_reshape: bool = True
    pause_on_low_confidence: bool = False


class CapabilityRequirement(StrictModel):
    name: str
    minimum_score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(default=1.0, ge=0.0)


class TaskNode(StrictModel):
    id: str
    run_id: str
    title: str
    task_type: TaskType
    input_refs: list[str] = Field(default_factory=list)
    output_schema: str = "structured_json"
    dependencies: list[str] = Field(default_factory=list)
    required_capabilities: dict[str, float] = Field(default_factory=dict)
    criticality: Criticality = Criticality.MEDIUM
    max_cost_tier: CostTier = CostTier.MEDIUM
    timeout_seconds: int = 300
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    fallback_policy: FallbackPolicy = Field(default_factory=FallbackPolicy)
    status: TaskStatus = TaskStatus.PENDING


class TaskDAG(StrictModel):
    run_id: str
    nodes: list[TaskNode]

    def node_ids(self) -> set[str]:
        return {node.id for node in self.nodes}

    def validate_graph(self) -> None:
        ids = self.node_ids()
        for node in self.nodes:
            missing = [dep for dep in node.dependencies if dep not in ids]
            if missing:
                raise ValueError(f"Task {node.id} has unknown dependencies: {missing}")
        self.topological_order()

    def topological_order(self) -> list[TaskNode]:
        nodes = {node.id: node for node in self.nodes}
        permanent: set[str] = set()
        temporary: set[str] = set()
        ordered: list[TaskNode] = []

        def visit(node_id: str) -> None:
            if node_id in permanent:
                return
            if node_id in temporary:
                raise ValueError(f"Cycle detected at task {node_id}")
            temporary.add(node_id)
            for dependency in nodes[node_id].dependencies:
                visit(dependency)
            temporary.remove(node_id)
            permanent.add(node_id)
            ordered.append(nodes[node_id])

        for node_id in nodes:
            visit(node_id)
        return ordered


class ProviderHealth(StrictModel):
    status: ProviderStatus = ProviderStatus.UNKNOWN
    latency_ms: int | None = None
    reliability_score: float = Field(default=0.5, ge=0.0, le=1.0)
    message: str = ""


class ProviderDescriptor(StrictModel):
    id: str
    kind: ProviderKind
    enabled: bool = True
    capabilities: dict[str, float] = Field(default_factory=dict)
    cost_tier: CostTier = CostTier.MEDIUM
    context_limit_tokens: int = 16_000
    health: ProviderHealth = Field(default_factory=ProviderHealth)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def supports(self, requirements: dict[str, float]) -> bool:
        return all(self.capabilities.get(name, 0.0) >= minimum for name, minimum in requirements.items())


class CostEstimate(StrictModel):
    tier: CostTier
    estimated_tokens: int = 0
    estimated_usd: float | None = None


class ProviderTask(StrictModel):
    task: TaskNode
    prompt: str
    context: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True
    allow_network: bool = False
    timeout_seconds: int = 300


class ProviderResult(StrictModel):
    provider_id: str
    status: TaskStatus
    output: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    cost_estimate: CostEstimate | None = None


class RoutingDecision(StrictModel):
    task_id: str
    action: RoutingAction
    provider_id: str | None = None
    score: float = 0.0
    reason: str
    alternatives: list[str] = Field(default_factory=list)


class ExecutionResult(StrictModel):
    task_id: str
    provider_id: str | None
    status: TaskStatus
    output: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime = Field(default_factory=utc_now)


class ScheduledTaskRecord(StrictModel):
    task_id: str
    status: TaskStatus
    attempt: int = 0
    dependencies: list[str] = Field(default_factory=list)
    cache_key: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class ScheduleReport(StrictModel):
    run_id: str
    records: list[ScheduledTaskRecord]
    execution_order: list[str]
    parallel_batches: list[list[str]]
    cache_hits: list[str] = Field(default_factory=list)
    failed_tasks: list[str] = Field(default_factory=list)


class ValidationFinding(StrictModel):
    validator: str
    passed: bool
    severity: Literal["info", "low", "medium", "high", "critical"]
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class QualityScore(StrictModel):
    completeness: int = Field(ge=0, le=100)
    factuality: int = Field(ge=0, le=100)
    citation_support: int = Field(ge=0, le=100)
    style_quality: int = Field(ge=0, le=100)
    continuity: int = Field(ge=0, le=100)
    cost_efficiency: int = Field(ge=0, le=100)
    artifact_integrity: Literal["pass", "fail"]
    code_validation: Literal["pass", "fail", "not_applicable"]


class QualityGateResult(StrictModel):
    passed: bool
    scores: QualityScore
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    repair_task_ids: list[str] = Field(default_factory=list)


class Artifact(StrictModel):
    id: str = Field(default_factory=lambda: new_id("artifact"))
    type: ArtifactType
    name: str
    path: str
    content_hash: str | None = None
    size_bytes: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def as_path(self) -> Path:
        return Path(self.path)


class ProductPackage(StrictModel):
    run_id: str
    final_markdown: str
    summary: str
    rejected_fragments: list[str] = Field(default_factory=list)
    artifact_requests: list[str] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)


class RuntimeEvent(StrictModel):
    run_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class RunManifest(StrictModel):
    run_id: str
    invocation: HostInvocation
    state: RunState
    context_manifest_path: str
    product_contract_path: str
    task_dag_path: str
    quality_report_path: str
    artifacts: list[Artifact]
    warnings: list[str] = Field(default_factory=list)
    routing_decisions: list[RoutingDecision] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None


class RunResult(StrictModel):
    run_id: str
    state: RunState
    artifact_dir: str
    manifest: RunManifest
    quality: QualityGateResult
