import re
from decimal import Decimal
from typing import Any

from caseproof.domain.money_text import AMBIGUOUS_AMOUNT, fragmented_money

STRICT = {
    "amount",
    "currency",
    "txn_datetime",
    "transaction_reference",
    "payee_vpa",
    "caller_number",
    "deception_channel",
    "caller_claimed_identity",
    "scam_instruction",
    "customer_statement",
    "embedded_instruction",
}
INJECTION = re.compile(
    (
        "ignore.*instructions|system prompt|set the case complete|m"
        "ark.*case.*complete|use .*as the reference|request.*OTP|ov"
        "erride.*rules"
    ),
    re.I,
)


def normalized(text: Any) -> str:
    """Normalize a scalar claim value for source-line comparisons."""
    return re.sub(r"[\s,]", "", str(text)).casefold()


def instruction_anchors(segments: Any) -> set[str]:
    """Find instruction spans across OCR line wraps without tainting unrelated observations."""
    by_artifact: dict[str, list[Any]] = {}
    for segment in segments:
        by_artifact.setdefault(segment.artifact_id, []).append(segment)
    unsafe: set[str] = set()
    for lines in by_artifact.values():
        offsets = []
        cursor = 0
        for line in lines:
            offsets.append((cursor, cursor + len(line.text), line.segment_id))
            cursor += len(line.text) + 1
        joined = " ".join(line.text for line in lines)
        for match in INJECTION.finditer(joined):
            unsafe.update(
                id for start, end, id in offsets if start < match.end() and end > match.start()
            )
    return unsafe


def supported(claim: Any, segments: Any) -> bool:
    """Check that every strict claim value occurs in its cited source lines."""
    texts = [segments[s].text for s in claim.anchor_segment_ids if s in segments]
    if claim.normalized_value is None:
        return False
    if claim.kind == "amount":
        if type(claim.normalized_value) is not int:
            return False
        try:
            value = int(claim.normalized_value)
        except (TypeError, ValueError):
            return False
        for text in texts:
            for n in re.findall(r"(?<![\w])\d[\d,]*(?:\.\d{1,2})?(?![\w])", text):
                try:
                    if int(Decimal(n.replace(",", "")) * 100) == value:
                        return True
                except Exception:
                    pass
        return False
    if claim.kind == "txn_datetime":
        time_value = str(claim.normalized_value)
        date = re.search(r"\d{4}-\d{2}-\d{2}", time_value)
        time = re.search(r"T(\d{2}:\d{2})", time_value)
        return bool(
            date
            and any(date[0] in t for t in texts)
            and (not time or any(time[1] in t for t in texts))
        )
    if claim.kind == "currency":
        return str(claim.normalized_value) == "INR" and any(
            re.search(r"₹|\bINR(?=\s|\d|$)|\bRs\.?(?=\s|\d|$)", t, re.I) for t in texts
        )
    if claim.kind == "deception_channel":
        terms = {
            "phone": ["call", "phone"],
            "sms": ["sms", "text message"],
            "chat": ["chat", "message"],
        }.get(str(claim.normalized_value).casefold(), [])
        return any(term in t.casefold() for term in terms for t in texts)
    if any(normalized(claim.normalized_value) in normalized(t) for t in texts):
        return True
    if claim.kind in {"scam_instruction", "customer_statement", "caller_claimed_identity"}:
        cited = [segments[s] for s in claim.anchor_segment_ids if s in segments]
        ordered = list(segments)
        indices = [ordered.index(s.segment_id) for s in cited]
        if (
            1 < len(cited) <= 6
            and len({s.artifact_id for s in cited}) == 1
            and indices == list(range(indices[0], indices[0] + len(indices)))
        ):
            return normalized(claim.normalized_value) in normalized(" ".join(texts))
    return False


def validate_claims(claims: Any, segments: Any) -> Any:
    """Reject unknown anchors and mark unsupported values unresolved."""
    by = {s.segment_id: s for s in segments}
    unsafe = instruction_anchors(segments)
    out = []
    for c in claims:
        if not c.anchor_segment_ids or any(s not in by for s in c.anchor_segment_ids):
            raise ValueError("unknown_anchor")
        c = c.model_copy(deep=True)
        if c.kind != "embedded_instruction" and unsafe.intersection(c.anchor_segment_ids):
            c.evidence_state = "unresolved"
            c.confidence_note = "embedded_instruction_anchor"
        elif (
            c.kind == "amount"
            and c.normalized_value is None
            and any(fragmented_money(by[a].text) for a in c.anchor_segment_ids)
        ):
            c.evidence_state = "unresolved"
            c.confidence_note = AMBIGUOUS_AMOUNT
        elif c.kind in STRICT and not supported(c, by):
            c.evidence_state = "unresolved"
            c.confidence_note = "invalid_quote"
        elif c.kind == "caller_claimed_identity":
            c.evidence_state = "reported"
            c.confidence_note = "Caller identity is reported, never verified"
        elif c.evidence_state not in ("reported", "conflicted", "unresolved"):
            c.evidence_state = "source_supported"
        out.append(c)
    return out
