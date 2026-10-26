"""Clearly marked practice evidence; never creates bank records or extraction answers."""

import re
import textwrap
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Literal

from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

from caseproof.domain.contracts import hash_json


class SampleEvidence(BaseModel):
    transaction_id: str = Field(max_length=120)
    kind: Literal["receipt", "messages", "call_log"]
    narrative: str = Field(default="", max_length=10000)
    ai: bool = False


def capabilities(o):
    provider = o.llm
    return {
        "synthetic": True,
        "ai_available": provider.provider in {"gemini", "vertex"}
        and provider.mode == "live"
        and not provider.init_error,
        "ai_provider": provider.provider,
        "samples": ["receipt", "messages", "call_log"],
    }


def render_sample(o, person_account, transaction, body):
    lines = {
        "receipt": ["Payment successful", "Bank-simulator record; not a real payment receipt."],
        "messages": [
            "Caller: Your account is at risk. Transfer money to a safe account.",
            "Customer: I made the payment while you were on the call.",
            "Caller: Do not contact the bank yet.",
            "Customer: I now believe I was deceived.",
        ],
        "call_log": [
            "Incoming call - fictional support caller",
            "Duration: 08:24",
            "Customer reports a safe-account scam.",
        ],
    }[body.kind]
    generator = "bank-simulator"
    if body.ai:
        if not capabilities(o)["ai_available"]:
            raise HTTPException(503, "AI sample generation is unavailable in this provider mode.")
        schema = {
            "type": "object",
            "properties": {"lines": {"type": "array", "items": {"type": "string"}}},
            "required": ["lines"],
        }
        try:
            result = o.llm.generate(
                "DEMO-" + hash_json(person_account)[:20],
                "demo-evidence",
                {"kind": body.kind, "customer_narrative": body.narrative, "synthetic": True},
                schema,
            )
            generated = result["data"]["lines"]
            if not isinstance(generated, list) or not 1 <= len(generated) <= 6:
                raise ValueError("invalid sample")
            if any(not isinstance(line, str) or not 1 <= len(line) <= 180 for line in generated):
                raise ValueError("invalid sample")
            if any(
                re.search(r"\d|₹|@|https?://|\b(?:INR|OTP|PIN|password)\b", line, re.I)
                for line in generated
            ):
                raise ValueError("model invented a protected payment or credential field")
            lines = generated
            generator = o.llm.provider + ":" + o.llm.model_id
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                503, "AI sample generation failed; retry or use a simulator sample."
            ) from None
    # Monetary anchors come exclusively from the selected server-owned bank row.
    header = [
        "CASEPROOF - SYNTHETIC PRACTICE EVIDENCE",
        body.kind.replace("_", " ").title() + " - " + generator,
        "FICTIONAL SAMPLE - NOT ORIGINAL CUSTOMER EVIDENCE",
    ]
    if body.kind == "receipt":
        local = datetime.fromisoformat(transaction["ts"]).astimezone(
            timezone(timedelta(hours=5, minutes=30))
        )
        header += [
            f"INR {transaction['amount_minor'] / 100:.2f}",
            f"Date: {local:%Y-%m-%d}",
            f"Time: {local:%H:%M} IST",
            "To: " + transaction["payee"],
            "Reference crop not included",
        ]
    else:
        header.append("Scenario: " + transaction["txn_id"])
    rendered = [part for line in header + lines for part in textwrap.wrap(line, 88)]
    # Use Pillow's embedded sans font consistently on the API and cloud images.
    # The dotted VPA can lose a low-confidence prefix in monospaced OCR. Improve
    # the actual practice pixels rather than guessing a missing payee from bank data.
    font = ImageFont.load_default(size=26)
    image = Image.new("RGB", (1500, 70 + len(rendered) * 80), "white")
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(rendered):
        draw.text((35, 35 + index * 80), line, font=font, fill="#172f40")
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue(), generator
