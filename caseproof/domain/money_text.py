"""Recognise ambiguous scalar money text without guessing missing grouping."""

import re

AMBIGUOUS_AMOUNT = "ambiguous_amount_tokens"
_PREFIX = r"(?:(?:amount[: ]+\s*)?(?:₹|Rs\.?|INR)|amount[: ]+)"
_FRAGMENT = re.compile(r"^\s*" + _PREFIX + r"\s*\d[\d,]*\s+\d[\d,. ]*\s*$", re.I)
COMPLETE_MONEY = re.compile(r"^\s*" + _PREFIX + r"\s*\d[\d,]*(?:\.\d{1,2})?\s*$", re.I)


def fragmented_money(text):
    return bool(_FRAGMENT.fullmatch(text))
