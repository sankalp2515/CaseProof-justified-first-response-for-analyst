import re
from decimal import Decimal

from caseproof.domain.contracts import CandidateClaim, ExtractionResult, RunMeta, hash_json
from caseproof.domain.money_text import AMBIGUOUS_AMOUNT, fragmented_money


class LiteralExtractor:
    """Deterministic literal observations; no model, fixture or label access."""

    def extract_claims(self, case_id, revision, segments):
        claims = []

        def add(s, kind, value, state="source_supported", text=None):
            uncertain = kind == "txn_datetime" and (s.ocr_model_id or "").endswith(
                ":uncertain-timestamp"
            )
            if uncertain:
                state = "reported"
            if state == "source_supported" and s.source == "text_line":
                state = "reported"
            if value is not None:
                claims.append(
                    CandidateClaim(
                        claim_id=f"cl-{s.segment_id}-{kind}-{len(claims)}",
                        kind=kind,
                        normalized_value=value,
                        original_text=text or s.text,
                        anchor_segment_ids=[s.segment_id],
                        evidence_state=state,
                        confidence_note=(
                            "OCR timestamp remains low confidence after repeated pixel reads; "
                            "verify the image."
                            if uncertain
                            else ""
                        ),
                    )
                )

        for s in segments:
            t = s.text
            if re.search(
                (
                    "ignore.*instructions|system prompt|mark.*complete|request."
                    "*OTP|override|verified.*caller|set the case complete|use ."
                    "*as the reference"
                ),
                t,
                re.I,
            ):
                add(s, "embedded_instruction", t, "reported")
                continue
            if fragmented_money(t):
                claims.append(
                    CandidateClaim(
                        claim_id=f"cl-{s.segment_id}-amount-{len(claims)}",
                        kind="amount",
                        normalized_value=None,
                        original_text=t,
                        anchor_segment_ids=[s.segment_id],
                        evidence_state="unresolved",
                        confidence_note=AMBIGUOUS_AMOUNT,
                    )
                )
            else:
                for m in re.finditer(
                    r"(?:\u20b9|Rs\.?|INR|amount[: ]+)\s*([\d,]+(?:\.\d{1,2})?)", t, re.I
                ):
                    add(s, "amount", int(Decimal(m[1].replace(",", "")) * 100))
            if re.search(r"\u20b9|\bRs\.?(?=\s|\d|$)|\bINR(?=\s|\d|$)", t, re.I):
                add(s, "currency", "INR")
            m = re.search(
                r"\b(20\d{2}-\d{2}-\d{2})(?:[ T]+(?:at\s+|around\s+)?"
                r"(\d{2}:\d{2})(?::(\d{2}))?(Z|[+-]\d{2}:?\d{2})?)?",
                t,
            )
            if m:
                zone = m[4] or "+05:30"
                if zone == "Z":
                    zone = "+00:00"
                elif len(zone) == 5:
                    zone = zone[:3] + ":" + zone[3:]
                value = m[1] + ("T" + m[2] + ":" + (m[3] or "00") + zone if m[2] else "")
                add(s, "txn_datetime", value)
            # OCR can insert spaces inside an identifier. Join only a labelled
            # payee line; the value guard still requires the full value in that line.
            payee_text = t
            if re.match(r"^(?:To|Payee):\s*", t, re.I):
                payee_text = re.sub(r"\s+", "", re.sub(r"^(?:To|Payee):\s*", "", t, flags=re.I))
            for m in re.finditer(
                r"[a-zA-Z0-9_.+-]+@(?:fictional\.invalid|cedardemo)(?![A-Za-z0-9_.+-])",
                payee_text,
                re.I,
            ):
                add(s, "payee_vpa", m[0].lower())
            for m in re.finditer(r"\bSYNTH-(?:TX|REF)-[A-Z0-9]+(?:-[A-Z0-9]+)*\b", t):
                if m[0].startswith(("SYNTH-TX-", "SYNTH-REF-")):
                    add(s, "transaction_reference", m[0])
            m = re.search(r"\+91[ -]+00000[ -]+0\d{4}", t)
            if m:
                add(s, "caller_number", m[0])
            if re.search(r"bank|officer|customer care|police", t, re.I) and re.search(
                r"caller|claimed|pretend|said|call", t, re.I
            ):
                add(s, "caller_claimed_identity", t, "reported")
            if re.search(
                r"safe account|safe-account|refund|transfer.*security|scam|fraud|impersonat|dhokha",
                t,
                re.I,
            ):
                add(s, "scam_instruction", t, "reported")
            if re.search(
                r"confirm|I paid|I sent|transferred|mera|maine|did not authorise", t, re.I
            ):
                add(s, "customer_statement", t, "reported")
        for c in claims:
            if c.kind == "txn_datetime" and "T" not in str(c.normalized_value):
                same = [
                    s
                    for s in segments
                    if s.artifact_id
                    == next(
                        s.artifact_id for s in segments if s.segment_id == c.anchor_segment_ids[0]
                    )
                ]
                timed = next(
                    (
                        (s, re.search(r"(?:Time:|around|at)\s*(\d{2}:\d{2})", s.text, re.I))
                        for s in same
                        if re.search(r"(?:Time:|around|at)\s*(\d{2}:\d{2})", s.text, re.I)
                    ),
                    None,
                )
                if timed:
                    seg, m = timed
                    c.normalized_value = str(c.normalized_value) + "T" + m[1] + ":00+05:30"
                    if seg.segment_id not in c.anchor_segment_ids:
                        c.anchor_segment_ids.append(seg.segment_id)
        return ExtractionResult(
            case_id=case_id,
            source_revision=revision,
            claims=claims,
            run=RunMeta(input_digest=hash_json([s.model_dump() for s in segments])),
        )
