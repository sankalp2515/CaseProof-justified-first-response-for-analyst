from datetime import datetime, timedelta

from caseproof.cloud.bank_network import cash_outs
from local_services.bank_network import BankNetwork


def world():
    return BankNetwork._generate(None, "net", 1234, "judge-test", minutes_ago=10)


def test_cash_outs_appear_only_once_their_time_has_passed():
    saved = world()
    scam = next(t for t in saved["dataset"]["transactions"] if t["txn_id"].endswith("-T1"))
    start = datetime.fromisoformat(scam["ts"])
    assert cash_outs(saved, (start + timedelta(minutes=10)).isoformat()) == []
    early = cash_outs(saved, (start + timedelta(minutes=25)).isoformat())
    assert [w["txn_id"].rsplit("-", 1)[1] for w in early] == ["ATM1"]
    late = cash_outs(saved, (start + timedelta(minutes=60)).isoformat())
    assert len(late) == 4 and all(w["channel"] == "ATM" for w in late)
    # Never withdraws more than the account held at its last report.
    for index in (0, 1):
        account = saved["reports"][index]["account"]
        taken = sum(w["amount_minor"] for w in late if w["from_account"] == account)
        assert taken == saved["reports"][index]["balance_minor"]
