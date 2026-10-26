from types import SimpleNamespace

from caseproof.genai import verify_intake, verify_reading, verify_sentences

SOURCES = [
    {"id": "P-T1", "text": "Bank ledger: confirmed_disputed debit of ₹45,000 to scam@ybl"},
    {"id": "K", "text": "49 minutes since the first debit; golden hour remaining 11 minutes"},
]


def test_sentences_need_known_sources_and_traceable_numbers():
    kept, dropped = verify_sentences(
        [
            {"text": "₹45,000 went to scam@ybl.", "source_ids": ["P-T1"]},
            {"text": "Only 11 minutes remain.", "source_ids": ["K"]},
            {"text": "₹90,000 is at risk.", "source_ids": ["P-T1"]},  # invented number
            {"text": "Funds went to scam@ybl.", "source_ids": ["X"]},  # unknown source
            {"text": "No citation.", "source_ids": []},
            {"text": "₹45,000 left 11 minutes ago.", "source_ids": ["P-T1"]},  # 11 not in P-T1
        ],
        SOURCES,
    )
    assert [k["text"] for k in kept] == ["₹45,000 went to scam@ybl.", "Only 11 minutes remain."]
    assert dropped == 4


def test_reading_findings_must_be_literally_in_cited_lines():
    lines = [
        SimpleNamespace(segment_id="s1", text="Paid to scam@ybl"),
        SimpleNamespace(segment_id="s2", text="UTR 412345678901"),
    ]
    findings, signals, dropped = verify_reading(
        {
            "findings": [
                {"label": "UPI ID", "value": "scam@ybl", "segment_ids": ["s1"]},
                {"label": "UTR", "value": "412345678901", "segment_ids": ["s1"]},  # wrong line
                {"label": "Amount", "value": "₹50,000", "segment_ids": ["s9"]},  # no such line
            ],
            "scam_signals": [{"signal": "Safe account lure", "segment_ids": ["s1"]}],
        },
        lines,
    )
    assert [f["label"] for f in findings] == ["UPI ID"]
    assert signals == [{"signal": "Safe account lure", "segment_ids": ["s1"]}]
    assert dropped == 2


def test_intake_quotes_must_come_from_the_narrative():
    narrative = "Bank se call aaya, unhone bola paise safe account me bhejo. Maine 45000 bheje."
    present, questions = verify_intake(
        {
            "facts": [
                {"fact": "contact_channel", "quote": "Bank se call aaya", "question": "q"},
                {"fact": "amount", "quote": "Maine 45000 bheje", "question": "q"},
                {"fact": "payee", "quote": "scam@ybl", "question": "Paise kis UPI ID par gaye?"},
            ]
        },
        narrative,
    )
    assert {p["fact"] for p in present} == {"contact_channel", "amount"}
    payee = next(q for q in questions if q["fact"] == "payee")
    assert payee["question"] == "Paise kis UPI ID par gaye?"
    # Facts Gemini skipped still get a rule-based question.
    assert any(q["fact"] == "credentials_shared" and q["question"] for q in questions)
