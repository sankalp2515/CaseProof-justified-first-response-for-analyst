from caseproof.domain.handoff_document import render_document


def test_readable_handoff_preserves_approved_identity_paths_and_escapes_evidence():
    packet = {
        "packet_id": "PK-1",
        "revision": 7,
        "summary": "<script>alert(1)</script>",
        "audit": {"digest": "approved-digest"},
        "report_update": {
            "traced_amounts": [
                {
                    "account": "Bank <A>",
                    "amount_minor": 7500,
                    "status": "recoverable",
                    "path": ["T1", "T2"],
                    "sources": ["ledger:T1", "cfcfrms_update:U1"],
                }
            ],
            "balance_observations": [{"update_id": "U1", "balance_minor": 7500}],
        },
    }
    html = render_document(packet)
    assert "approved-digest" in html and "revision 7" in html
    assert "INR 75.00" in html and "T1 → T2" in html
    assert "ledger:T1; cfcfrms_update:U1" in html
    assert "&lt;script&gt;" in html and "<script>" not in html
    assert "Bank &lt;A&gt;" in html and "Print / Save as PDF" in html
    assert "U1" in html and "not confirmed holds or recovery" in html
