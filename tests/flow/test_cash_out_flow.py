import caseproof.cloud.bank_network as network
from tests.flow import test_google_backend_contract as contract


def test_full_cloud_flow_still_reconciles_when_every_cash_out_is_due(tmp_path, monkeypatch):
    monkeypatch.setattr(network, "CASH_OUT_PLAN", ((0, 0, 2), (1, 0, 2), (0, 0, 1), (1, 0, 1)))
    seen = []
    original = network.cash_outs
    monkeypatch.setattr(network, "cash_outs", lambda *a: seen.extend(original(*a)) or original(*a))
    contract.test_new_cloud_complaint_request_reply_approval_and_two_deliveries(
        tmp_path, monkeypatch
    )
    assert seen, "at least one cash-out was revealed by the refresh"


def test_repeat_complaints_for_one_payment_link_once_and_settle(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from caseproof.adapters.firestore_casestore import identity
    from caseproof.cloud.app import create_app
    from caseproof.domain.contracts import Actor

    o, tasks, receiver, clean = contract.runtime(tmp_path, monkeypatch)
    actor = Actor(user_id="bank-simulator", role="admin", tenant_id="demo")
    world = network.CloudBankNetwork(o).seed_tenant(actor)
    o.store.documents.transact(
        lambda tx: tx.set(
            "demo_catalogues/" + identity("demo"), {"tenant": "demo", "catalogue": world}
        )
    )
    tasks.drain(o, receiver)
    with TestClient(create_app(o.s, o), base_url="https://caseproof.test") as client:
        account = world["customers"][0]
        client.post("/v1/victim/sessions", json={"customer_id": account["account"]})
        t1 = next(
            t
            for t in client.get("/v1/victim/me").json()["transactions"]
            if t["txn_id"].endswith("-T1")
        )
        ids = []
        for n in (1, 2):
            body = {
                "submission_id": f"repeat-{n}",
                "narrative": "The caller told me to move money to a safe account.",
                "transaction_ids": [t1["txn_id"]],
                "payment_authorisation": "deceived",
            }
            ids.append(client.post("/v1/victim/complaints", json=body).json()["case_id"])
            tasks.drain(o, receiver)
        first, second = (o.store.get(cid) for cid in ids)
        assert [link.complaint_id for link in second.linked] == [ids[0]]
        revisions = (first.revision, second.revision)
        tasks.drain(o, receiver)
        # Settled: draining again changes nothing (no wake-up loop).
        assert (o.store.get(ids[0]).revision, o.store.get(ids[1]).revision) == revisions
