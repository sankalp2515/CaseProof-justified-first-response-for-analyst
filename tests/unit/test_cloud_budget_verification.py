from copy import deepcopy

import pytest

from scripts.cloud_foundation import validate_budget


def budget():
    return {
        "budgetFilter": {"creditTypesTreatment": "EXCLUDE_ALL_CREDITS"},
        "amount": {"specifiedAmount": {"currencyCode": "INR", "units": "2000"}},
        "thresholdRules": [{"thresholdPercent": n} for n in [0.25, 0.5, 0.8, 1]],
        "notificationsRule": {"disableDefaultIamRecipients": False},
    }


def test_budget_accepts_api_omitted_false_and_explicit_current_spend_defaults():
    expected = budget()
    actual = deepcopy(expected)
    actual["notificationsRule"] = {}
    for rule in actual["thresholdRules"]:
        rule["spendBasis"] = "CURRENT_SPEND"
    validate_budget(actual, expected)


@pytest.mark.parametrize("drift", ["recipients", "thresholds", "forecast", "credits", "amount"])
def test_budget_drift_fails_closed(drift):
    expected = budget()
    actual = deepcopy(expected)
    if drift == "recipients":
        actual["notificationsRule"]["disableDefaultIamRecipients"] = True
    elif drift == "thresholds":
        actual["thresholdRules"] = []
    elif drift == "forecast":
        actual["thresholdRules"][0]["spendBasis"] = "FORECASTED_SPEND"
    elif drift == "credits":
        actual["budgetFilter"]["creditTypesTreatment"] = "INCLUDE_ALL_CREDITS"
    else:
        actual["amount"]["specifiedAmount"]["units"] = "20000"
    with pytest.raises(RuntimeError, match="budget"):
        validate_budget(actual, expected)
