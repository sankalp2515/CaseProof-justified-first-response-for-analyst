"""Literal text checks preserve reported observations a model might omit."""

from typing import Any

from caseproof.adapters.literal_extractor import LiteralExtractor
from caseproof.domain.contracts import CandidateClaim
from caseproof.domain.validator import instruction_anchors, validate_claims


def preserve_text_observations(proposed: Any, segments: Any) -> Any:
    """Retain explicit customer text observations with their original anchors."""
    text = [s for s in segments if s.source == "text_line"]
    literal = LiteralExtractor().extract_claims("literal-validation", 0, text).claims
    kinds = {
        "amount",
        "currency",
        "txn_datetime",
        "transaction_reference",
        "payee_vpa",
        "caller_number",
        "embedded_instruction",
    }
    out = list(proposed)

    def key(c):
        return c.kind, str(c.normalized_value), tuple(sorted(c.anchor_segment_ids))

    seen = {key(c) for c in out}
    for c in literal:
        if c.kind in kinds and key(c) not in seen:
            c.confidence_note = (
                "Deterministic literal-text safety observation; not model verification"
            )
            out.append(c)
            seen.add(key(c))
    unsafe = instruction_anchors(segments)
    for segment in segments:
        if segment.segment_id in unsafe and not any(
            c.kind == "embedded_instruction" and segment.segment_id in c.anchor_segment_ids
            for c in out
        ):
            out.append(
                CandidateClaim(
                    claim_id="pending-instruction",
                    kind="embedded_instruction",
                    normalized_value=segment.text,
                    original_text=segment.text,
                    anchor_segment_ids=[segment.segment_id],
                    evidence_state="reported",
                    confidence_note="Wrapped untrusted instruction; never executable",
                )
            )
    return validate_claims(out, segments)
