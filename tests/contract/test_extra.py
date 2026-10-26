import pytest
from pydantic import ValidationError

from caseproof.domain.contracts import CaseSnapshot, Segment


def test_box_coordinates_checked():
    with pytest.raises(ValidationError):
        Segment(segment_id="s", artifact_id="a", text="hi", box_2d=[10, 5, 4, 20])


def test_digest_changes_with_evidence():
    s = CaseSnapshot(case_id="x", revision=1).seal()
    assert s.valid_digest()
    s.revision = 2
    assert not s.valid_digest()
