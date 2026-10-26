"""Bounded live foundation checks; writes only clearly labeled synthetic validation records.

Run as a module from the repo root: python -m scripts.cloud_smoke [--vertex].
This verifies service connectivity, not the full migrated complaint workflow.
"""

import argparse
import json
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.genai import types

from caseproof.adapters.gcs_storage import GCSStorage
from caseproof.adapters.gemini_llm import client
from caseproof.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vertex", action="store_true", help="Make one bounded Mumbai AI call")
    args = parser.parse_args()
    cfg = json.loads((ROOT / "infra/google/foundation.json").read_text())
    project, region = cfg["project_id"], cfg["region"]
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    result = {"project": project, "region": region}

    storage = GCSStorage(cfg["bucket"], session=session)
    data = b"CaseProof synthetic cloud storage validation 2026-10-15"
    key, digest = storage.put(data, "text/plain")
    assert storage.read(key) == data
    assert storage.put(data, "text/plain") == (key, digest)
    result["gcs"] = {"create_read_duplicate_verified": True, "key": key}
    print("GCS checks passed", flush=True)

    documents = (
        f"https://firestore.googleapis.com/v1/projects/{project}"
        "/databases/(default)/documents/_caseproof_validation"
    )
    fields = {"purpose": {"stringValue": "synthetic-foundation-connectivity-v1"}}
    response = session.post(
        documents, params={"documentId": "foundation-v1"}, json={"fields": fields}, timeout=30
    )
    if response.status_code != 409:
        response.raise_for_status()
    response = session.get(documents + "/foundation-v1", timeout=30)
    response.raise_for_status()
    assert response.json()["fields"] == fields
    result["firestore"] = {"create_only_validation_document_read": True}
    print("Firestore connectivity passed (case-store migration still pending)", flush=True)

    response = session.post(
        f"https://bigquery.googleapis.com/bigquery/v2/projects/{project}/queries",
        json={
            "query": "SELECT 41 + 1 AS validation_result",
            "useLegacySql": False,
            "location": region,
            "maximumBytesBilled": "10485760",
            "timeoutMs": 10000,
        },
        timeout=30,
    )
    response.raise_for_status()
    query = response.json()
    assert query["jobComplete"] and query["rows"][0]["f"][0]["v"] == "42"
    result["bigquery"] = {
        "bounded_query_passed": True,
        "bytes_processed": query.get("totalBytesProcessed"),
        "job": query.get("jobReference"),
    }
    print("BigQuery bounded SQL passed (bank adapter migration still pending)", flush=True)

    if args.vertex:
        settings = Settings(
            _env_file=None,
            llm_provider="vertex",
            google_cloud_project=project,
            google_cloud_location=region,
            gemini_model="gemini-2.5-flash",
        )
        with client(settings) as ai:
            response = ai.models.generate_content(
                model=settings.gemini_model,
                contents="Return JSON with ok set to true.",
                config=types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=64,
                    automatic_continuation=False,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                    response_mime_type="application/json",
                    response_json_schema={
                        "type": "object",
                        "properties": {"ok": {"type": "boolean"}},
                        "required": ["ok"],
                    },
                ),
            )
        assert json.loads(response.text)["ok"] is True
        result["vertex"] = {
            "model": settings.gemini_model,
            "regional_response_valid": True,
            "usage": response.usage_metadata.model_dump(mode="json"),
        }
        print("Vertex structured JSON passed in Mumbai", flush=True)

    output = ROOT / "var/cloud-setup/smoke-result.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Saved nonsecret proof to {output}")


if __name__ == "__main__":
    main()
