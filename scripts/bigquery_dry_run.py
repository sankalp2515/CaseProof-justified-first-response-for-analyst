"""Dry-run every BigQuery statement the cloud adapters issue against real BigQuery.

Usage: python scripts/bigquery_dry_run.py [project] [dataset] [location]
Dry runs validate syntax, types and table schemas without reading or writing
data or incurring query charges. Offline tests use a semantic double, so this
is the check that the production SQL itself is valid.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import google.auth  # noqa: E402
from google.auth.transport.requests import AuthorizedSession  # noqa: E402

from caseproof.adapters.bigquery_bank import BigQuery, BigQueryBank  # noqa: E402
from caseproof.adapters.bigquery_graph import BigQueryGraph  # noqa: E402

project, dataset, location = (
    sys.argv[1:4] + ["caseproof-511713", "caseproof_bank", "asia-south1"][len(sys.argv[1:4]) :]
)
credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
session = AuthorizedSession(credentials)
results = []


class DryRun(BigQuery):
    def query(self, sql, parameters):
        response = self.session.post(
            f"https://bigquery.googleapis.com/bigquery/v2/projects/{self.project}/queries",
            json={
                "query": sql,
                "useLegacySql": False,
                "location": self.location,
                "dryRun": True,
                "parameterMode": "NAMED",
                "queryParameters": [
                    {"name": k, "parameterType": {"type": "STRING"}, "parameterValue": {"value": v}}
                    for k, v in parameters.items()
                ],
            },
            timeout=30,
        )
        name = sys._getframe(1).f_code.co_name
        if response.status_code >= 400:
            message = response.json().get("error", {}).get("message", response.text[:300])
            results.append((name, False, message))
        else:
            results.append((name, True, ""))
        return []


client = DryRun(project, dataset, location, session=session)
bank = BigQueryBank(client, "judge-dry-run", None)
NOW = "2026-10-17T10:00:00+00:00"
bank.batches()
bank.batches(NOW)
bank.transactions("ACC-DRY-RUN", NOW)
bank.complaints("2026-10-17T09:00:00+00:00", NOW)
for table in ("bank_batches", "downstream_reports", "complaints"):
    client.publish(table, "judge-dry-run", "ID-DRY", "digest", '{"reported_at": "' + NOW + '"}')
try:
    BigQueryGraph(bank).read(NOW)
except Exception as error:  # empty dry-run rows may stop later Python steps
    results.append(("graph_read_python", True, type(error).__name__))

failed = [r for r in results if not r[1]]
for name, passed, message in results:
    print(("PASS " if passed else "FAIL ") + name, message)
sys.exit(1 if failed else 0)
