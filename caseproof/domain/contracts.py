import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


def now() -> str:
    """Return the current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> str:
    """Serialize JSON deterministically for revision and packet hashes."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def hash_json(value: Any) -> str:
    """Hash the canonical JSON representation with SHA-256."""
    return sha256(canonical(value).encode()).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Actor(Contract):
    user_id: str
    role: Literal["analyst", "reviewer", "admin"]
    tenant_id: str


class ArtifactRef(Contract):
    artifact_id: str
    case_id: str
    kind: Literal["narrative", "receipt", "messages", "call_log", "other"]
    mime_type: str
    sha256: str
    byte_count: int
    object_key: str
    received_at: str = Field(default_factory=now)
    stage: Literal["initial", "followup"] = "initial"


class Segment(Contract):
    segment_id: str
    artifact_id: str
    page_index: int = 0
    text: str
    box_2d: list[int] | None = None
    source: Literal["text_line", "model_ocr"] = "text_line"
    ocr_model_id: str | None = None

    @field_validator("box_2d")
    @classmethod
    def box_valid(cls, v: Any) -> Any:
        """Validate a normalized image box without changing its coordinates."""
        if v is not None and (
            len(v) != 4 or any(x < 0 or x > 1000 for x in v) or v[0] >= v[2] or v[1] >= v[3]
        ):
            raise ValueError("invalid box")
        return v


class CandidateClaim(Contract):
    claim_id: str
    kind: Literal[
        "amount",
        "currency",
        "txn_datetime",
        "transaction_reference",
        "payee_vpa",
        "deception_channel",
        "caller_claimed_identity",
        "caller_number",
        "scam_instruction",
        "customer_statement",
        "embedded_instruction",
    ]
    normalized_value: str | StrictInt | None = None
    original_text: str = ""
    anchor_segment_ids: list[str] = Field(default_factory=list)
    evidence_state: Literal["reported", "source_supported", "conflicted", "unresolved"] = "reported"
    materiality: bool = True
    confidence_note: str = ""


class RunMeta(Contract):
    mode: Literal["live", "mock", "cache", "local"] = "mock"
    provider: str = "mock"
    model_id: str = "rules-v1"
    prompt_hash: str = ""
    schema_version: str = "1"
    input_digest: str = ""
    latency_ms: float = 0
    tokens_in: int = 0
    tokens_out: int = 0


class ExtractionResult(Contract):
    case_id: str
    source_revision: int
    claims: list[CandidateClaim] = Field(default_factory=list)
    unresolved_fields: list[str] = Field(default_factory=list)
    run: RunMeta = Field(default_factory=RunMeta)


class LedgerMatch(Contract):
    claim_ids: list[str]
    txn_id: str
    match_fields: list[str]
    resolved_fields: dict[str, Any]
    source: Literal["ledger:synthetic"] = "ledger:synthetic"


class UnreportedTransfer(Contract):
    reference: str | None = None
    txn_id: str
    amount_minor: int
    payee: str
    ts: str
    reason_codes: list[str]


class LinkedComplaint(Contract):
    complaint_id: str
    link_type: Literal["payee_vpa", "caller_number", "device"]
    shared_value: str
    reported_at: str
    amount_minor: int


class Gap(Contract):
    gap_id: str
    required_fact: str
    status: Literal["missing", "conflicting", "unconfirmed"] = "missing"
    resolvable_by: Literal["ledger", "customer", "none"] = "customer"


class EvidenceRequest(Contract):
    request_id: str
    catalogue_id: str
    resolves_gap_ids: list[str] = Field(default_factory=list)
    score: int = 0
    score_components: dict[str, int] = Field(default_factory=dict)
    state: Literal[
        "proposed",
        "accepted",
        "fulfilled",
        "unavailable",
        "skipped",
        "superseded",
        "suppressed",
        "blocked",
    ] = "proposed"
    reason: str = ""
    reminder: str = "Report on 1930 / cybercrime.gov.in now; don't wait for this request"
    explanation: dict[str, list[str]] = Field(
        default_factory=lambda: {"can_settle": [], "cannot_prove": []}
    )


class ClockState(Contract):
    first_debit_at: str | None = None
    as_of: str
    minutes_since_first_debit: float | None = None
    golden_hour_remaining: float | None = None
    recoverable_now: int = 0
    replay: bool = False


class ReadinessAssessment(Contract):
    disposition: Literal["REVIEW_REQUIRED", "COMPLETE_CANDIDATE", "ESCALATE_CANDIDATE"] = (
        "REVIEW_REQUIRED"
    )
    clock: dict = Field(default_factory=dict)
    satisfied_facts: list[str] = Field(default_factory=list)
    unresolved_facts: list[str] = Field(default_factory=list)
    blocking_conflicts: list[str] = Field(default_factory=list)
    policy_version: str = "demo-policy-v2"


class Fact(Contract):
    fact_id: str
    kind: str
    value: str | int | None
    sources: list[str]
    states: list[str]
    claim_ids: list[str]


class CaseSnapshot(Contract):
    case_id: str
    revision: int
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    claims: list[CandidateClaim] = Field(default_factory=list)
    clock: ClockState | None = None
    trail: dict = Field(default_factory=dict)
    facts: list[Fact] = Field(default_factory=list)
    ledger_matches: list[LedgerMatch] = Field(default_factory=list)
    unreported: list[UnreportedTransfer] = Field(default_factory=list)
    linked: list[LinkedComplaint] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    requests: list[EvidenceRequest] = Field(default_factory=list)
    readiness: ReadinessAssessment = Field(default_factory=ReadinessAssessment)
    corrections: list[dict] = Field(default_factory=list)
    run_meta: list[RunMeta] = Field(default_factory=list)
    digest: str = ""

    def seal(self) -> Any:
        """Compute and attach the canonical digest of this snapshot."""
        self.digest = hash_json(self.model_dump(mode="json", exclude={"digest"}))
        return self

    def valid_digest(self) -> bool:
        """Check that persisted content matches its canonical digest."""
        return self.digest == hash_json(self.model_dump(mode="json", exclude={"digest"}))


class Approval(Contract):
    approval_id: str
    case_id: str
    revision: int
    digest: str
    disposition: Literal["COMPLETE_HANDOFF", "ESCALATE_WITH_GAPS"]
    reviewer: Actor
    clock_at_approval: ClockState | None = None
    reason: str
    at: str = Field(default_factory=now)


class PacketManifest(Contract):
    packet_id: str
    approval_id: str
    revision: int
    synthetic: Literal[True] = True
    summary: str
    investigation_brief: dict = Field(default_factory=dict)
    claims_with_sources: list[dict]
    facts: list[Fact] = Field(default_factory=list)
    report_update: dict = Field(default_factory=dict)
    transactions: list[dict]
    linked: list[dict]
    unresolved: list[dict]
    request_history: list[dict]
    audit: dict


class OutboundMessage(Contract):
    kind: Literal["cfcfrms_report_update", "case_ticket"]
    payload: dict
    idempotency_key: str
    status: str = "pending"
