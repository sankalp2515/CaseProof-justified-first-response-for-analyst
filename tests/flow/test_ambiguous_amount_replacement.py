from caseproof.adapters.provider import Provider
from local_services.bank_network import BankNetwork
from local_services.demo_world import ADMIN
from tests.flow.test_api import client


def test_uncertain_amount_blocks_review_then_corroborated_replacement_allows_it(tmp_path):
    with client(tmp_path) as c:
        o = c.app.state.orchestrator
        o.s.llm_provider = "local"
        o.s.external_worker = True
        o.s.trail_feed_path = tmp_path / "feed.json"
        o.llm = Provider(o.s)
        network = BankNetwork(o)
        manifest = network.create("AMOUNT-REPLACEMENT", 791, ADMIN)
        txs = network.read(manifest["network_id"], ADMIN)["dataset"]["transactions"][2:4]
        s = o.store.create(
            "REPLACEMENT-FLOW",
            customer_account=manifest["customer_account"],
            reported_at=manifest["reported_at"],
            first_contact=manifest["first_contact"],
            selected_transaction_ids=[t["txn_id"] for t in txs],
        )
        o.intake.add(
            s.case_id,
            b"A caller pretended to be a bank officer. I sent money to a safe account.",
            "text/plain",
            "narrative",
        )
        money = f"{txs[0]['amount_minor'] / 100:.2f}"
        original = o.intake.add(
            s.case_id,
            ("INR " + money[:3] + " " + money[3:] + "\n" + txs[0]["reference"]).encode(),
            "text/plain",
            "receipt",
        )
        original_hash = original.artifacts[-1].sha256
        blocked = o.process(s.case_id)
        assert "readable_receipt" in blocked.readiness.unresolved_facts
        assert any(
            r.catalogue_id == "request_readable_receipt" and r.state == "proposed"
            for r in blocked.requests
        )
        assert any(x.kind == "amount" and x.normalized_value is None for x in blocked.claims)
        review = {
            "expected_revision": blocked.revision,
            "digest": blocked.digest,
            "disposition": "COMPLETE_HANDOFF",
            "reason": "Checked sources",
        }
        assert (
            c.post(
                f"/v1/cases/{s.case_id}/reviews", json=review, headers={"X-Demo-User": "reviewer"}
            ).status_code
            == 422
        )
        o.intake.add(
            s.case_id,
            ("INR " + money + "\n" + txs[0]["reference"]).encode(),
            "text/plain",
            "receipt",
        )
        ready = o.process(s.case_id)
        assert ready.readiness.disposition == "COMPLETE_CANDIDATE"
        assert any(a.sha256 == original_hash for a in ready.artifacts)
        assert o.store.get(s.case_id, blocked.revision).digest == blocked.digest
        assert o.store.get(s.case_id, blocked.revision).valid_digest()
        response = c.post(
            f"/v1/cases/{s.case_id}/reviews",
            json={**review, "expected_revision": ready.revision, "digest": ready.digest},
            headers={"X-Demo-User": "reviewer"},
        )
        assert response.status_code == 200, response.text


def test_readability_reply_is_bound_to_the_requested_original_in_immutable_history(tmp_path):
    from caseproof.adapters.customer_links import CustomerLinks
    from caseproof.domain.readiness import needs_readable_receipt

    with client(tmp_path) as c:
        o = c.app.state.orchestrator
        o.s.customer_portal = True
        o.s.llm_provider = "local"
        o.s.external_worker = True
        o.s.trail_feed_path = tmp_path / "feed.json"
        o.llm = Provider(o.s)
        network = BankNetwork(o)
        manifest = network.create("SCOPED-REPLACEMENT", 901, ADMIN)
        txs = network.read(manifest["network_id"], ADMIN)["dataset"]["transactions"][2:4]
        s = o.store.create(
            "SCOPED-REPLACEMENT",
            customer_account=manifest["customer_account"],
            reported_at=manifest["reported_at"],
            first_contact=manifest["first_contact"],
            selected_transaction_ids=[t["txn_id"] for t in txs],
        )
        original = o.intake.add(s.case_id, b"The scan is unreadable", "text/plain", "receipt")
        original_id = original.artifacts[-1].artifact_id
        blocked = o.process(s.case_id)
        request = next(r for r in blocked.requests if r.state == "proposed")
        assert request.catalogue_id == "request_readable_receipt"
        links = CustomerLinks(o)
        link = links.issue(s.case_id, request.request_id)
        token = link["url"].rsplit("/", 1)[1]
        links.upload(
            token,
            f"INR {txs[0]['amount_minor'] / 100:.2f}\n{txs[0]['reference']}".encode(),
            "text/plain",
            "receipt",
        )
        uploaded = o.store.get(s.case_id)
        reply = next(r for r in uploaded.requests if r.request_id == request.request_id)
        assert reply.explanation["receipt_artifact_ids"] == [original_id]
        assert reply.explanation["replacement_artifact_ids"] == [uploaded.artifacts[-1].artifact_id]
        assert needs_readable_receipt(uploaded)
        reissued = links.issue(s.case_id, request.request_id)
        token = reissued["url"].rsplit("/", 1)[1]
        after_reissue = o.store.get(s.case_id)
        kept = next(r for r in after_reissue.requests if r.request_id == request.request_id)
        assert kept.explanation["replacement_artifact_ids"] == [uploaded.artifacts[-1].artifact_id]
        links.upload(
            token,
            f"INR {txs[0]['amount_minor'] / 100:.2f}\n{txs[0]['reference']}".encode(),
            "text/plain", "receipt",
        )
        assert len(o.store.get(s.case_id).artifacts) == 2
        links.complete(token)
        ready = o.process(s.case_id)
        assert not needs_readable_receipt(ready)
        assert o.store.get(s.case_id, blocked.revision).digest == blocked.digest
        assert o.store.get(s.case_id, blocked.revision).valid_digest()
        assert ready.artifacts[0].sha256 == original.artifacts[0].sha256
        later = o.intake.add(s.case_id, b"A second unreadable scan", "text/plain", "receipt")
        later_id = later.artifacts[-1].artifact_id
        pending = o.process(s.case_id)
        next_request = next(r for r in pending.requests if r.state == "proposed")
        links.issue(s.case_id, next_request.request_id)
        scoped = o.store.get(s.case_id)
        next_reply = next(r for r in scoped.requests if r.request_id == next_request.request_id)
        assert next_reply.explanation["receipt_artifact_ids"] == [later_id]
