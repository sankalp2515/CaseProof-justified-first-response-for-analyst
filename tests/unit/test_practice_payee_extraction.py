import pytest

from caseproof.adapters.literal_extractor import LiteralExtractor
from caseproof.domain.contracts import Segment


@pytest.mark.parametrize(
    "handle,expected",
    [
        ("narmada.traders.acdefhkmnp@cedardemo", True),
        ("old-payee@fictional.invalid", True),
        ("narmada.traders.acdefhkmnp@cedardemo.other", False),
        ("narmada.traders.acdefhkmnp@cedardemox", False),
    ],
)
def test_local_payee_extraction_preserves_complete_identifier(handle, expected):
    claims = (
        LiteralExtractor()
        .extract_claims("CASE", 1, [Segment(segment_id="s", artifact_id="a", text="To: " + handle)])
        .claims
    )
    payees = [c.normalized_value for c in claims if c.kind == "payee_vpa"]
    assert payees == ([handle] if expected else [])
