from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from secrets import token_hex
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    stamp = utc_now().strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}_{stamp}_{token_hex(4)}"


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
    ROUTING = "routing"
    EXECUTING = "executing"
    REPAIR_EXECUTION = "repair_execution"
    FINAL_ASSEMBLY = "final_assembly"
    VALIDATION = "validation"
    ARTIFACT_BUILD = "artifact_build"
    ARTIFACT_VALIDATION = "artifact_validation"
    PACKAGING = "packaging"
    DELIVERED = "delivered"
    NEEDS_ATTENTION = "needs_attention"
    CANCELLED = "cancelled"
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
    CANCELLED = "cancelled"
    WAITING_FOR_USER = "waiting_for_user"


SUCCESS_TASK_STATUSES = {TaskStatus.COMPLETED, TaskStatus.CACHED}


def task_succeeded(status: TaskStatus | str) -> bool:
    return status in SUCCESS_TASK_STATUSES


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
    allow_cloud: bool = False
    allowed_url_hosts: list[str] = Field(default_factory=list)
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
    content_text: str = ""
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
    chunks: list[ContextChunk] = Field(default_factory=list)
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
    source_name: str = ""
    source_uri: str = ""
    chunk_locators: dict[str, str] = Field(default_factory=dict)
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
    cacheable: bool = True
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
    input_tokens: int = 0
    output_tokens: int = 0
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


class ProviderRoutingMetric(StrictModel):
    task_id: str
    provider_id: str
    enabled: bool
    health_status: ProviderStatus
    reliability_score: float = Field(ge=0.0, le=1.0)
    cost_tier: CostTier
    capability_score: float = Field(default=0.0, ge=0.0)
    cost_score: float = Field(default=0.0, ge=0.0, le=1.0)
    total_score: float = Field(default=0.0, ge=0.0)
    eligible: bool = False
    supports_requirements: bool = False
    rejection_reasons: list[str] = Field(default_factory=list)


class TaskRoutingTelemetry(StrictModel):
    task_id: str
    selected_provider_id: str | None = None
    selected_action: RoutingAction
    selected_score: float = 0.0
    metrics: list[ProviderRoutingMetric] = Field(default_factory=list)


class RoutingTelemetryReport(StrictModel):
    run_id: str
    provider_count: int = 0
    task_telemetry: list[TaskRoutingTelemetry] = Field(default_factory=list)


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


class TaskBudget(StrictModel):
    task_id: str
    original_max_cost_tier: CostTier
    enforced_max_cost_tier: CostTier
    estimated_tokens: int = 0
    token_budget: int = 0
    estimated_usd: float | None = None
    reason: str = ""


class UsageLedgerEntry(StrictModel):
    task_id: str
    provider_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_usd: float | None = None
    token_budget: int = 0
    within_token_budget: bool = True
    estimated: bool = True


class BudgetReport(StrictModel):
    run_id: str
    requested_profile: BudgetProfile
    effective_max_cost_tier: CostTier
    total_estimated_tokens: int = 0
    total_token_budget: int = 0
    total_estimated_usd: float | None = None
    enforced: bool = True
    task_budgets: list[TaskBudget] = Field(default_factory=list)
    usage_ledger: list[UsageLedgerEntry] = Field(default_factory=list)
    usage_reconciled: bool = False
    warnings: list[str] = Field(default_factory=list)


class DeltaTaskDecision(StrictModel):
    task_id: str
    action: Literal["execute", "reuse"]
    reason: str
    cache_key: str | None = None
    previous_run_id: str | None = None


class DeltaExecutionPlan(StrictModel):
    run_id: str
    previous_run_id: str | None = None
    input_hash_changed: bool = True
    changed_input_ids: list[str] = Field(default_factory=list)
    reusable_task_ids: list[str] = Field(default_factory=list)
    executable_task_ids: list[str] = Field(default_factory=list)
    task_decisions: list[DeltaTaskDecision] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TraceSpan(StrictModel):
    name: str
    started_at: datetime
    completed_at: datetime
    duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObservabilityReport(StrictModel):
    run_id: str
    spans: list[TraceSpan] = Field(default_factory=list)
    final_state: RunState | None = None
    event_count: int = 0
    artifact_count: int = 0
    warning_count: int = 0


class DebugBundleManifest(StrictModel):
    run_id: str
    artifact_names: list[str] = Field(default_factory=list)
    report_names: list[str] = Field(default_factory=list)
    trace_names: list[str] = Field(default_factory=list)
    redaction_notice: str = "Secrets are redacted from summaries; raw user files are not copied into this manifest."
    safe_to_share: bool = False


class EvidenceAuditFinding(StrictModel):
    kind: str
    passed: bool
    severity: Literal["info", "low", "medium", "high", "critical"]
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceClaim(StrictModel):
    task_id: str
    claim: str
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_required: bool = True
    resolved: bool = False


class EvidenceAuditReport(StrictModel):
    run_id: str
    passed: bool
    source_count: int = 0
    provenance_count: int = 0
    cited_source_ids: list[str] = Field(default_factory=list)
    unsupported_task_ids: list[str] = Field(default_factory=list)
    invalid_evidence_refs: list[str] = Field(default_factory=list)
    unconsumed_evidence_refs: list[str] = Field(default_factory=list)
    claims: list[EvidenceClaim] = Field(default_factory=list)
    findings: list[EvidenceAuditFinding] = Field(default_factory=list)


class ApprovalGate(StrictModel):
    name: str
    required: bool = False
    granted: bool = False
    blocking: bool = False
    severity: Literal["info", "low", "medium", "high", "critical"] = "info"
    reason: str = ""


class ApprovalReport(StrictModel):
    run_id: str
    gates: list[ApprovalGate] = Field(default_factory=list)
    blocked: bool = False
    warnings: list[str] = Field(default_factory=list)


class EgressDecision(StrictModel):
    subject: str
    allowed: bool
    reason: str
    input_ids: list[str] = Field(default_factory=list)


class ExecutionPolicy(StrictModel):
    schema_version: str = "1.0"
    run_id: str
    privacy_mode: PrivacyMode
    allow_network_fetch: bool = False
    allow_hosted_models: bool = False
    allow_private_data_egress: bool = False
    allow_shell: bool = False
    allow_repo_writes: bool = False
    private_input_ids: list[str] = Field(default_factory=list)
    decisions: list[EgressDecision] = Field(default_factory=list)


class ValidationCommandResult(StrictModel):
    command: str
    cwd: str
    status: Literal["passed", "failed", "skipped", "blocked"]
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    reason: str = ""


class RepoValidationReport(StrictModel):
    run_id: str
    executed: bool = False
    passed: bool = True
    command_results: list[ValidationCommandResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ArtifactIntegrityEntry(StrictModel):
    name: str
    path: str
    artifact_type: ArtifactType
    exists: bool = False
    size_bytes: int | None = None
    content_hash: str | None = None
    hash_matches: bool = False
    errors: list[str] = Field(default_factory=list)


class ArtifactIntegrityReport(StrictModel):
    run_id: str
    passed: bool = False
    artifact_count: int = 0
    duplicate_names: list[str] = Field(default_factory=list)
    missing_expected: list[str] = Field(default_factory=list)
    entries: list[ArtifactIntegrityEntry] = Field(default_factory=list)


class ValidationFinding(StrictModel):
    validator: str
    passed: bool
    severity: Literal["info", "low", "medium", "high", "critical"]
    message: str
    pass_message: str
    fail_message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class QualityScore(StrictModel):
    completeness: int = Field(ge=0, le=100)
    parse_confidence: int = Field(ge=0, le=100)
    citation_support: int = Field(ge=0, le=100)
    continuity: int = Field(ge=0, le=100)
    routing_efficiency: int = Field(ge=0, le=100)
    artifact_presence: Literal["pass", "fail"]
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
    schema_version: str = "2.0"
    run_id: str
    invocation: HostInvocation
    state: RunState
    context_manifest_path: str
    product_contract_path: str
    task_dag_path: str
    quality_report_path: str
    checksums_path: str | None = None
    delivery_receipt_path: str | None = None
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
