from pathlib import Path

from caseproof.domain.contracts import CandidateClaim, Segment
from caseproof.domain.evidence import apply_corrections


def test_prompt_distinguishes_scam_directions_from_model_commands():
    prompt = Path("caseproof/prompts/extract-v2.md").read_text()
    assert "scam_instruction" in prompt and "NOT an embedded_instruction" in prompt


def test_correction_cannot_follow_reused_id_to_different_kind():
    s = Segment(segment_id="s", artifact_id="a", text="INR 100 and caller Cedar Bank")
    a = CandidateClaim(
        claim_id="c", kind="amount", normalized_value=20000, anchor_segment_ids=["s"]
    )
    other = CandidateClaim(
        claim_id="old",
        kind="caller_claimed_identity",
        normalized_value="Cedar Bank",
        anchor_segment_ids=["s"],
    )
    out = apply_corrections(
        [other, a],
        [dict(claim_id="old", kind="amount", value=10000, reason="typo", anchor_segment_ids=["s"])],
        [s],
    )
    assert out[0].normalized_value == "Cedar Bank"
    assert out[1].normalized_value == 10000
