import pytest

from caseproof.adapters.literal_extractor import LiteralExtractor
from caseproof.domain.contracts import Segment
from caseproof.domain.ledger import dt


@pytest.mark.parametrize(
    "source,expected",
    [
        ("Payment time: 2026-10-17T14:00:00+00:00", "2026-10-17T19:30:00+05:30"),
        ("Payment time: 2026-10-17T14:00:20Z", "2026-10-17T19:30:20+05:30"),
        ("Payment time: 2026-10-17T19:30:00+0530", "2026-10-17T19:30:00+05:30"),
        ("2026-10-17 at 19:30", "2026-10-17T19:30:00+05:30"),
    ],
)
def test_explicit_offsets_are_preserved_and_unzoned_local_time_uses_ist(source, expected):
    result = LiteralExtractor().extract_claims(
        "TEST",
        1,
        [
            Segment(segment_id="line", artifact_id="receipt", text=source),
        ],
    )
    claim = next(c for c in result.claims if c.kind == "txn_datetime")
    assert dt(claim.normalized_value) == dt(expected)
