"""Regression of every authored scenario through the real Docker API and local OCR."""

import json
import os
import time

import httpx

from caseproof.config import Settings
from caseproof.pipeline.load import read_artifact


def main():
    settings = Settings()
    root = settings.eval_kit_v3
    client = httpx.Client(
        base_url=os.environ.get("API_BASE_URL", "http://api:8000"), timeout=60, trust_env=False
    )
    manifest = json.loads((root / "inputs/manifest.json").read_text())
    predictions = []
    output = settings.data_dir / "local_scenarios.json"

    def call(method, path, **kwargs):
        result = client.request(method, path, **kwargs)
        result.raise_for_status()
        return result.json()

    def wait(job):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            status = call("GET", "/v1/jobs/" + job)
            if status["status"] in ("done", "failed", "stale"):
                assert status["status"] == "done", status
                return
            time.sleep(0.2)
        raise AssertionError("worker timed out")

    for item in manifest["cases"]:
        fixture = item["case_id"]
        loaded = call("POST", "/v1/local/fixtures/" + fixture)
        wait(loaded["job_id"])
        cid = loaded["case_id"]
        snap = call("GET", "/v1/cases/" + cid)
        initial = snap["readiness"]["disposition"]
        requests = [r for r in snap["requests"] if r["state"] == "proposed"]
        selected = requests[0]["catalogue_id"] if requests else None
        # The customer simulator alone reveals artifacts after the actual chosen request.
        from mock_services.customer import response

        if requests:
            reply = response(root, fixture, selected)
            if reply["available"] and reply["artifacts"]:
                link = call("POST", f"/v1/cases/{cid}/requests/{requests[0]['request_id']}/send")
                token = link["url"].rsplit("/", 1)[1]
                for artifact in reply["artifacts"]:
                    call(
                        "POST",
                        f"/v1/customer/{token}/artifacts",
                        data={"kind": artifact["kind"]},
                        files={
                            "file": (
                                "evidence",
                                read_artifact(root, artifact),
                                artifact["mime_type"],
                            )
                        },
                    )
                result = call("POST", f"/v1/customer/{token}/complete", json={})
                wait(result["job_id"])
                snap = call("GET", "/v1/cases/" + cid)
        totals = {}
        for position in snap["trail"].get("positions", []):
            totals[position["account"]] = (
                totals.get(position["account"], 0) + position["amount_minor"]
            )
        row = {
            "fixture": fixture,
            "case_id": cid,
            "initial": initial,
            "request": selected,
            "final": snap["readiness"]["disposition"],
            "trace_by_account": totals,
            "unresolved": snap["readiness"]["unresolved_facts"],
            "all_runs_local": all(r["mode"] == "local" for r in snap["run_meta"]),
        }
        row["export_passed"] = False
        row["blocked_delivery_verified"] = False
        if item["family"] == "unreadable":
            # Authored external-bank scenarios deliberately contain no own-bank rows.
            # Policy v3 requires bank verification even after a readable upload. Preserve
            # the old labels and separately verify the stricter bank/approval boundary.
            from caseproof.adapters.duckdb_bank import DuckDBBank

            assert not DuckDBBank(settings.duckdb_path).transactions(fixture + "-CUSTOMER")
            assert not snap["ledger_matches"]
            assert selected == "request_readable_receipt"
            assert any(
                r["catalogue_id"] == selected and r["state"] == "fulfilled"
                for r in snap["requests"]
            )
            followup_receipts = {
                a["artifact_id"]
                for a in snap["artifacts"]
                if a["kind"] == "receipt" and a["stage"] == "followup"
            }
            assert any(s["artifact_id"] in followup_receipts for s in snap["segments"])
            assert {"amount", "date", "transaction_reference", "deception_account"} <= set(
                snap["readiness"]["satisfied_facts"]
            )
            assert set(row["unresolved"]) == {
                "bank_verified",
                "ledger_coverage",
                "all_transfers_accounted",
            }
            rejected = client.post(
                f"/v1/cases/{cid}/reviews",
                headers={"X-Demo-User": "reviewer"},
                json={
                    "expected_revision": snap["revision"],
                    "digest": snap["digest"],
                    "disposition": "COMPLETE_HANDOFF",
                    "reason": "Bank verification absent",
                },
            )
            assert rejected.status_code == 422
            rejected = client.post(f"/v1/cases/{cid}/exports", headers={"X-Demo-User": "reviewer"})
            assert rejected.status_code == 409
            row["blocked_delivery_verified"] = True
        if row["final"] in {"COMPLETE_CANDIDATE", "ESCALATE_CANDIDATE"}:
            headers = {"X-Demo-User": "reviewer"}
            call(
                "POST",
                f"/v1/cases/{cid}/reviews",
                headers=headers,
                json={
                    "expected_revision": snap["revision"],
                    "digest": snap["digest"],
                    "disposition": "COMPLETE_HANDOFF"
                    if row["final"] == "COMPLETE_CANDIDATE"
                    else "ESCALATE_WITH_GAPS",
                    "reason": "SIMULATED reviewer in complete local regression",
                },
            )
            packet = call("POST", f"/v1/cases/{cid}/exports", headers=headers)
            report = packet["packet"]["report_update"]
            assert report["debits"] and all(d["sources"] for d in report["debits"])
            assert len(packet["outbound"]) == 2 and packet["packet"]["audit"]["mode"] == "local"
            row["export_passed"] = True
        predictions.append(row)
        # Persist predictions before reading this case's answer label.
        output.write_text(json.dumps(predictions, indent=2))
        gold = json.loads((root / "labels" / (fixture + ".json")).read_text())
        expected = gold["after_followup"] if gold["has_followup"] else gold["initial"]
        row["legacy_expected_final"] = expected["disposition"]
        row["expected_final"] = (
            "REVIEW_REQUIRED" if item["family"] == "unreadable" else expected["disposition"]
        )
        row["policy_version"] = snap["readiness"]["policy_version"]
        row["trace_matches_independent_reference"] = totals == gold["trace_by_account"]
        row["passed"] = (
            row["final"] == row["expected_final"]
            and row["trace_matches_independent_reference"]
            and row["all_runs_local"]
            and (row["export_passed"] or row["blocked_delivery_verified"])
        )
        output.write_text(json.dumps(predictions, indent=2))
        print(fixture, row["final"], selected, "PASS" if row["passed"] else "FAIL", flush=True)
    summary = {
        "cases": len(predictions),
        "passed": sum(p["passed"] for p in predictions),
        "failures": [p for p in predictions if not p["passed"]],
    }
    (settings.data_dir / "local_scenario_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    assert not summary["failures"]


if __name__ == "__main__":
    main()
