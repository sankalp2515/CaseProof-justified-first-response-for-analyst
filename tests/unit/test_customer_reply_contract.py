from types import SimpleNamespace

import pytest

from caseproof.adapters.customer_links import CustomerLinks
from caseproof.cloud.customer_links import CustomerLinks as CloudCustomerLinks


@pytest.mark.parametrize("adapter", [CustomerLinks, CloudCustomerLinks])
def test_resolved_reply_contains_only_its_case_return_target(adapter):
    links = object.__new__(adapter)
    links.o = SimpleNamespace(store=SimpleNamespace(get=lambda cid: SimpleNamespace(requests=[])))
    links.resolve = lambda token: {
        "case_id": "CASE-scoped",
        "request_id": None,
        "uploads": 0,
        "expires": 9999999999,
    }
    result = links.describe("valid-test-capability")
    assert result["case_id"] == "CASE-scoped"
    assert "snapshots" not in result
