"""Integer-paisa contracts for the local temporal graph and trail snapshots."""

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class Account(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    bank: str
    label: str
    kind: Literal["customer", "beneficiary", "layer", "merchant", "cashout", "external"]
    opening_balance: int = Field(default=0, ge=0)


class Transfer(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    txn_id: str
    ts: str
    from_account: str = Field(validation_alias=AliasChoices("from_account", "from"))
    to_account: str = Field(validation_alias=AliasChoices("to_account", "to"))
    amount_minor: int = Field(gt=0)
    channel: str
    reference: str
    source: str = Field(pattern=r"^(ledger|cfcfrms_update:.+)$")


class ComplaintLink(BaseModel):
    complaint_id: str
    victim: str
    txn_id: str
    disputed_amount: int = Field(gt=0)
    reported_at: str


class Identifier(BaseModel):
    entity: str
    kind: Literal["caller_number", "device", "vpa"]
    value: str


class Position(BaseModel):
    complaint_id: str
    account: str
    amount_minor: int
    path: list[str]
    sources: list[str]
    status: Literal["recoverable", "unaccounted", "left_system"]


class TraceResult(BaseModel):
    rule: Literal["sop_v1"] = "sop_v1"
    positions: list[Position]
    account_vectors: dict[str, dict[str, int]]
    balances: dict[str, int]
    total_left_system: int
    summaries: dict[str, dict[str, int]]
    report_hash: str = ""
    feed_sources: list[str] = Field(default_factory=list)
