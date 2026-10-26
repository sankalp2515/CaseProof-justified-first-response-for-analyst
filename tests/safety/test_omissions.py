from caseproof.domain.contracts import ArtifactRef, CandidateClaim, CaseSnapshot, Segment
from caseproof.domain.evidence import merge_conflicts
from caseproof.pipeline.extract import preserve_text_observations


def test_model_omission_cannot_hide_reported_time_conflict():
    story = Segment(segment_id="n", artifact_id="N", text="I paid INR 100 on 2026-10-01 at 12:20.")
    receipt = Segment(
        segment_id="r", artifact_id="R", text="INR 100 on 2026-10-01 at 11:29", source="model_ocr"
    )
    proposed = [
        CandidateClaim(
            claim_id="m",
            kind="txn_datetime",
            normalized_value="2026-10-01T11:29:00+05:30",
            anchor_segment_ids=["r"],
            evidence_state="source_supported",
        )
    ]
    claims = preserve_text_observations(proposed, [story, receipt])
    assert any(c.kind == "txn_datetime" and "12:20" in str(c.normalized_value) for c in claims)

    def art(id, kind):
        return ArtifactRef(
            artifact_id=id,
            case_id="C",
            kind=kind,
            mime_type="text/plain",
            sha256="0" * 64,
            byte_count=1,
            object_key="x",
        )

    snapshot = CaseSnapshot(
        case_id="C",
        revision=1,
        segments=[story, receipt],
        claims=claims,
        artifacts=[art("N", "narrative"), art("R", "receipt")],
    )
    merge_conflicts(snapshot)
    assert any(
        c.evidence_state == "conflicted" for c in snapshot.claims if c.kind == "txn_datetime"
    )


def test_only_literal_observations_are_added():
    s = Segment(segment_id="s", artifact_id="a", text="Amount not known; reference cropped")
    assert preserve_text_observations([], [s]) == []
