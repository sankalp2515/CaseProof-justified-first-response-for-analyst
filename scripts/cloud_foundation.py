"""Inspect or provision the authorized CaseProof foundation using ADC, never exported keys.

Run from the repository root: python scripts/cloud_foundation.py [--apply].
No application services are deployed and no AI calls are made by this script.
"""

import argparse
import json
import time
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession

ROOT = Path(__file__).resolve().parents[1]


def validate_budget(actual, expected):
    """Refuse to label drifted spending alerts as working cost controls."""
    for field in ("budgetFilter", "amount"):
        if actual.get(field) != expected[field]:
            raise RuntimeError(f"Existing budget has incompatible {field}")

    def rules(value):
        return sorted(
            (rule["thresholdPercent"], rule.get("spendBasis", "CURRENT_SPEND"))
            for rule in value.get("thresholdRules", [])
        )

    if rules(actual) != rules(expected):
        raise RuntimeError("Existing budget has incompatible thresholdRules")
    for field, value in expected.get("notificationsRule", {}).items():
        if actual.get("notificationsRule", {}).get(field, False) != value:
            raise RuntimeError(f"Existing budget has incompatible notificationsRule.{field}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    cfg = json.loads((ROOT / "infra/google/foundation.json").read_text())
    project = cfg["project_id"]
    region = cfg["region"]
    if project != "caseproof-511713" or region != "asia-south1":
        raise ValueError("Unexpected target: review the script before changing project or region")
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    results = {}

    def request(method, url, **kwargs):
        response = session.request(method, url, timeout=60, **kwargs)
        if response.status_code == 404:
            return None
        if not response.ok:
            raise RuntimeError(f"{method} {url}: {response.status_code} {response.text[:1500]}")
        return response.json() if response.content else {}

    def ensure(label, url, create_url, body, required, params=None):
        current = request("GET", url)
        if current is None and args.apply:
            current = request("POST", create_url, json=body, params=params)
            if current and "name" in current and "/operations/" in current["name"]:
                # Firestore long-running creation; finite retries with visible progress.
                op = url.split("/v1/")[0] + "/v1/" + current["name"]
                for _ in range(24):
                    current = request("GET", op)
                    if current is None:
                        raise RuntimeError(f"Operation not found: {op}")
                    if current.get("done"):
                        if "error" in current:
                            raise RuntimeError(str(current["error"]))
                        break
                    print(f"Waiting for {label}", flush=True)
                    time.sleep(5)
                else:
                    raise RuntimeError(f"{label} creation still running; inspect before retry")
            for _ in range(6):
                current = request("GET", url)
                if current is not None:
                    break
                time.sleep(2)
            if current is None:
                raise RuntimeError(f"{label} was created but is not visible yet; retry inspection")
        if current is None:
            results[label] = {"status": "absent"}
        else:
            for key, expected in required.items():
                actual = current
                for part in key.split("."):
                    actual = actual.get(part, {})
                if str(actual).lower() != str(expected).lower():
                    raise RuntimeError(f"{label}: {key}={actual!r}, expected {expected!r}")
            results[label] = {"status": "verified", **required}
        print(label, json.dumps(results[label]), flush=True)
        return current

    billing = request(
        "GET", f"https://cloudbilling.googleapis.com/v1/projects/{project}/billingInfo"
    )
    if not billing or not billing.get("billingEnabled"):
        raise RuntimeError("Billing is not enabled")
    if billing["billingAccountName"] != "billingAccounts/" + cfg["billing_account"]:
        raise RuntimeError("Unexpected billing account")
    budget_url = f"https://billingbudgets.googleapis.com/v1/{billing['billingAccountName']}/budgets"
    budgets = request("GET", budget_url) or {}
    display_name = "CaseProof initial INR 2000 gross usage"
    matches = [b for b in budgets.get("budgets", []) if b.get("displayName") == display_name]
    budget_body = {
        "displayName": display_name,
        "budgetFilter": {
            "projects": ["projects/" + cfg["project_number"]],
            "calendarPeriod": "MONTH",
            "creditTypesTreatment": "EXCLUDE_ALL_CREDITS",
        },
        "amount": {
            "specifiedAmount": {
                "currencyCode": cfg["budget_currency"],
                "units": cfg["budget_units"],
            }
        },
        "thresholdRules": [{"thresholdPercent": n} for n in [0.25, 0.5, 0.8, 1.0]],
        "notificationsRule": {"disableDefaultIamRecipients": False},
    }
    if not matches and args.apply:
        matches = [request("POST", budget_url, json=budget_body)]
    if matches:
        budget = matches[0]
        validate_budget(budget, budget_body)
        results["budget"] = {
            "status": "verified",
            "name": budget["name"],
            "currency": cfg["budget_currency"],
            "units": cfg["budget_units"],
            "hard_cap": False,
            "credits_excluded": True,
        }
    else:
        results["budget"] = {"status": "absent"}
    print("budget", json.dumps(results["budget"]), flush=True)

    # Supported service-level caps complement, but cannot replace, the total alert.
    for label, service, amount in [
        ("vertex_spend_cap", "C7E2-9256-1C43", cfg["vertex_cap_units"]),
        ("run_spend_cap", "152E-C115-5142", cfg["run_cap_units"]),
    ]:
        name = "CaseProof " + label + " INR " + amount
        body = {
            "displayName": name,
            "budgetFilter": {
                "projects": ["projects/" + cfg["project_number"]],
                "services": ["services/" + service],
                "calendarPeriod": "MONTH",
                "creditTypesTreatment": "EXCLUDE_ALL_CREDITS",
            },
            "amount": {"specifiedAmount": {"currencyCode": "INR", "units": amount}},
            "thresholdRules": [{"thresholdPercent": n} for n in [0.5, 0.8, 1.0]],
            "notificationsRule": {
                "disableDefaultIamRecipients": False,
                "enableProjectLevelRecipients": True,
            },
            "spendCap": {"inputState": "CONFIGURED"},
        }
        found = [b for b in budgets.get("budgets", []) if b.get("displayName") == name]
        if not found and args.apply:
            found = [request("POST", budget_url, json=body)]
        if found:
            validate_budget(found[0], body)
            if found[0].get("spendCap", {}).get("outputState") != "CONFIGURED":
                raise RuntimeError(f"{label} is not configured; inspect billing before proceeding")
            results[label] = {
                "status": "verified",
                "currency": "INR",
                "units": amount,
                "spendCap": found[0]["spendCap"],
            }
        else:
            results[label] = {"status": "absent"}
        print(label, json.dumps(results[label]), flush=True)

    iam = f"https://iam.googleapis.com/v1/projects/{project}/serviceAccounts"
    email = f"{cfg['runtime_account']}@{project}.iam.gserviceaccount.com"
    ensure(
        "runtime_identity",
        iam + "/" + email,
        iam,
        {
            "accountId": cfg["runtime_account"],
            "serviceAccount": {"displayName": "CaseProof runtime"},
        },
        {"email": email},
    )
    bucket = cfg["bucket"]
    storage = "https://storage.googleapis.com/storage/v1/b"
    ensure(
        "evidence_bucket",
        storage + "/" + bucket,
        storage,
        {
            "name": bucket,
            "location": region,
            "storageClass": "STANDARD",
            "iamConfiguration": {
                "uniformBucketLevelAccess": {"enabled": True},
                "publicAccessPrevention": "enforced",
            },
            "softDeletePolicy": {"retentionDurationSeconds": "0"},
        },
        {
            "location": region,
            "iamConfiguration.uniformBucketLevelAccess.enabled": True,
            "iamConfiguration.publicAccessPrevention": "enforced",
        },
        {"project": project},
    )

    def bind_member(label, get_url, set_url, roles, *, storage_policy=False):
        current = request("GET", get_url) if storage_policy else request("POST", get_url, json={})
        member = "serviceAccount:" + email
        bindings = current.setdefault("bindings", [])
        missing = []
        for role in roles:
            binding = next(
                (b for b in bindings if b["role"] == role and not b.get("condition")), None
            )
            if binding is None:
                binding = {"role": role, "members": []}
                bindings.append(binding)
            if member not in binding["members"]:
                missing.append(role)
                binding["members"].append(member)
        if missing and args.apply:
            payload = current if storage_policy else {"policy": current}
            request("PUT" if storage_policy else "POST", set_url, json=payload)
        results[label] = {
            "status": "verified" if not missing or args.apply else "missing",
            "roles": roles,
        }
        print(label, json.dumps(results[label]), flush=True)

    if results["evidence_bucket"]["status"] == "verified":
        bind_member(
            "evidence_identity_access",
            storage + "/" + bucket + "/iam",
            storage + "/" + bucket + "/iam",
            ["roles/storage.objectCreator", "roles/storage.objectViewer"],
            storage_policy=True,
        )
    if results["runtime_identity"]["status"] == "verified":
        resource = f"https://cloudresourcemanager.googleapis.com/v1/projects/{project}"
        bind_member(
            "runtime_project_access",
            resource + ":getIamPolicy",
            resource + ":setIamPolicy",
            ["roles/aiplatform.user", "roles/bigquery.jobUser"],
        )
    firestore = f"https://firestore.googleapis.com/v1/projects/{project}/databases"
    ensure(
        "case_database",
        firestore + "/(default)",
        firestore,
        {
            "locationId": region,
            "type": "FIRESTORE_NATIVE",
            "databaseEdition": "STANDARD",
            "deleteProtectionState": "DELETE_PROTECTION_ENABLED",
        },
        {
            "locationId": region,
            "type": "FIRESTORE_NATIVE",
            "databaseEdition": "STANDARD",
            "deleteProtectionState": "DELETE_PROTECTION_ENABLED",
        },
        {"databaseId": "(default)"},
    )
    datasets = f"https://bigquery.googleapis.com/bigquery/v2/projects/{project}/datasets"
    ensure(
        "bank_dataset",
        datasets + "/" + cfg["dataset"],
        datasets,
        {
            "datasetReference": {"projectId": project, "datasetId": cfg["dataset"]},
            "location": region,
            "description": "CaseProof synthetic bank and downstream data",
            "access": [
                {"role": "OWNER", "specialGroup": "projectOwners"},
                {"role": "WRITER", "userByEmail": email},
            ],
        },
        {"location": region},
    )
    queues = f"https://cloudtasks.googleapis.com/v2/projects/{project}/locations/{region}/queues"
    queue = ensure(
        "processing_queue",
        queues + "/" + cfg["queue"],
        queues,
        {
            "name": queues.split("/v2/")[1] + "/" + cfg["queue"],
            "rateLimits": {"maxDispatchesPerSecond": 1, "maxConcurrentDispatches": 1},
            "retryConfig": {"maxAttempts": 3},
        },
        {
            "rateLimits.maxDispatchesPerSecond": 1,
            "rateLimits.maxConcurrentDispatches": 1,
            "retryConfig.maxAttempts": 3,
        },
    )
    if queue and args.apply and queue.get("state") != "PAUSED":
        request("POST", queues + "/" + cfg["queue"] + ":pause", json={})
    if queue:
        results["processing_queue"]["state"] = request("GET", queues + "/" + cfg["queue"])["state"]
    registry = (
        f"https://artifactregistry.googleapis.com/v1/projects/{project}"
        f"/locations/{region}/repositories"
    )
    ensure(
        "container_repository",
        registry + "/" + cfg["repository"],
        registry,
        {
            "format": "DOCKER",
            "description": "CaseProof prototype images",
            "cleanupPolicyDryRun": False,
            "cleanupPolicies": {
                "delete-old": {
                    "action": "DELETE",
                    "condition": {"tagState": "ANY", "olderThan": "604800s"},
                },
                "keep-latest": {"action": "KEEP", "mostRecentVersions": {"keepCount": 2}},
            },
        },
        {"format": "DOCKER"},
        {"repositoryId": cfg["repository"]},
    )

    output = ROOT / "var/cloud-setup/foundation-result.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"project": project, "region": region, "resources": results}, indent=2) + "\n"
    )
    print(f"Saved nonsecret inventory to {output}")


if __name__ == "__main__":
    main()
