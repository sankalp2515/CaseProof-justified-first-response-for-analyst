"""Deduplicated facts retain every raw claim's source and state."""

from caseproof.domain.contracts import CandidateClaim, Fact, hash_json


def merge_facts(claims: list[CandidateClaim]) -> list[Fact]:
    """Group normalized values without erasing disagreement or raw observations."""
    groups = {}
    for claim in claims:
        key = (claim.kind, str(claim.normalized_value).casefold())
        if key not in groups:
            groups[key] = Fact(
                fact_id="fact-" + hash_json(key)[:12],
                kind=claim.kind,
                value=claim.normalized_value,
                sources=[],
                states=[],
                claim_ids=[],
            )
        fact = groups[key]
        fact.sources = sorted(set(fact.sources + claim.anchor_segment_ids))
        fact.states = sorted(set(fact.states + [claim.evidence_state]))
        fact.claim_ids.append(claim.claim_id)
    return list(groups.values())
