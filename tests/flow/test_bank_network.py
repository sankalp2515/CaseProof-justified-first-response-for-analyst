from tests.flow.test_api import client


def test_network_has_bank_records_before_any_complaint_and_independent_receipt(tmp_path):
    with client(tmp_path) as c:
        body = {"network_id": "NEW-NETWORK", "seed": 41}
        assert c.post("/v1/local/bank-network", json=body).status_code == 403
        response = c.post("/v1/local/bank-network", json=body, headers={"X-Demo-User": "admin"})
        assert response.status_code == 200, response.text
        network = response.json()
        assert network["synthetic"] and len(network["customers"]) == 2
        assert c.get("/v1/cases").json() == []
        assert len(c.get("/v1/bank/customers").json()) == 2
        again = c.post("/v1/local/bank-network", json=body, headers={"X-Demo-User": "admin"}).json()
        assert network == again
        receipt = c.get(network["receipt_url"])
        assert receipt.status_code == 200 and receipt.content.startswith(b"\x89PNG")
        assert c.get(network["dataset_url"]).json()["synthetic"]
        assert (
            c.post(
                "/v1/local/bank-network",
                json={**body, "seed": 42},
                headers={"X-Demo-User": "admin"},
            ).status_code
            == 409
        )
        assert c.get("/simulator").status_code == 200
