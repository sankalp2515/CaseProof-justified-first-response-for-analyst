# Google staging deployment

**Current restoration and test status:** see [SUBMISSION_VERIFICATION.md](SUBMISSION_VERIFICATION.md). The record below describes the original deployment. Service caps are now Cloud Run INR 5,000 and Vertex AI INR 2,000; these are separate service-level caps. Model, image and runtime settings must be inspected rather than inferred from this historical record.

**Status: deployed on 17 October 2026 at the project owner's instruction.**
Public URL: **https://8-233-217-230.sslip.io** (`/app/#/entry`). Synthetic data only.

Project `caseproof-511713`, region `asia-south1` (Mumbai). Expected running cost is
roughly US$1–2 per day (load balancer and Cloud Armor are the fixed part; Cloud Run
scales to zero; Document AI and Gemini are charged per complaint). Budgets alert,
they do not stop charges; see **Rollback** to stop spending.

## Deployment record

| Item | Value |
| --- | --- |
| Domain | `8-233-217-230.sslip.io` → reserved global IP `8.233.217.230`, Google-managed certificate |
| Staff access | Practice personas (`practice_personas = true`): Analyst/Reviewer without sign-in, confined by the server to each visitor's own practice tenant; admin actions unavailable. Google sign-in remains available by setting `staff_audience`/`staff_principals` and building the frontend with `STAFF_ACCESS=google`. |
| Practice sessions | 50 per day (`CLOUD_PRACTICE_DAILY_LIMIT`) |
| Document AI | OCR processor `a9fd5b157a5792b6`, pinned Google Stable version `pretrained-ocr-v1.0-2020-09-23` |
| Gemini | `gemini-2.5-flash` on Vertex AI in `asia-south1` |
| Images | Built locally from this repository and pushed to Artifact Registry `asia-south1-docker.pkg.dev/caseproof-511713/caseproof`; deployed by digest |
| Terraform state | `gs://caseproof-511713-tfstate/runtime` (versioned, uniform access, public access prevented) |
| Variables | `infra/google/runtime/staging.tfvars` (git-ignored; holds digests and IDs, no secrets) |
| Dispatch | Cloud Tasks queue running; reconcile scheduler every minute |
| Alerts | Backend errors, queue backlog and queue delay → project owner email |

Issues found only against real Google services, and fixed:

1. Cloud Armor rejects regex capture groups; the victim throttle rule now uses path prefixes.
2. BigQuery requires `AS` for `STRUCT` field names; the transactions query failed. Every
   statement is now dry-run against real BigQuery by `scripts/bigquery_dry_run.py`.
3. Real Document AI version IDs contain dots; adapter validation rejected them.
4. Vertex returns transient `429 RESOURCE_EXHAUSTED` in Mumbai; the job budget was 3
   attempts inside a 5-minute circuit. Now 6 attempts over about 12 minutes with a
   60-second circuit, matching the Cloud Tasks retry policy.
5. New practice sessions publish bank records asynchronously; the frontend now waits on
   `503 bank_data_preparing` instead of showing an error.
6. Cloud Tasks dispatched one task at a time, so practice-bank publications queued ahead
   of complaint processing; now 5 concurrent dispatches and up to 3 worker instances.
7. BigQuery aborts concurrent multi-statement transactions on one table; publication is
   now a single atomic `MERGE` that still rejects a changed digest.

## Service topology

The local Compose stack and the cloud target use the same service boundaries.

| Service | Local (Compose) | Google staging (Cloud Run) | Image |
| --- | --- | --- | --- |
| frontend | nginx + React, proxies API paths to `api` | nginx + React, behind the HTTPS load balancer | `frontend/Dockerfile` (`FRONTEND_PROFILE=local` / `cloud`) |
| api | FastAPI, SQLite/DuckDB volume | FastAPI, Firestore/BigQuery/GCS | `Dockerfile` `service` target / `Dockerfile.cloud` |
| worker | Polling worker | Private service invoked by Cloud Tasks/Scheduler | `Dockerfile` `service` / `Dockerfile.cloud` |
| ocr | Tesseract service | Replaced by Document AI | `Dockerfile` `ocr` target (local only) |
| scanner | — | Private ClamAV service (resident `clamd`) | `Dockerfile.scanner` |
| simulator | Report receivers | Private hosted simulators | `Dockerfile` `service` / `Dockerfile.cloud` |
| trail-feed | Synthetic downstream feed | BigQuery publication | local only |

Load-balancer routing (`infra/google/runtime/edge.tf`): `/v1/*` and `/health` go to
the API; all other paths, including `/customer/{token}` links, go to the frontend.
The cloud frontend proxies nothing; it redirects capability links to the React
reply route, which validates them through `/v1/customer/{token}`.

## Inputs the project owner must supply

| Input | Terraform / build variable | Notes |
| --- | --- | --- |
| Public HTTPS domain | `public_domain` | DNS record pointed at the edge address after apply |
| Staff OAuth web client ID | `staff_audience`, Cloud Build `_STAFF_CLIENT_ID` | Same value for API audience and frontend sign-in |
| Staff Google subjects and roles | `staff_principals` | Map of Google subject → analyst/reviewer/admin |
| Document AI processor and pinned version | `processor_id`, `processor_version` | Mumbai availability and quota confirmed first |
| Gemini model and quota | `gemini_model` | Default `gemini-2.5-flash`; confirm regional quota |
| Alert destination | `alert_email` | Monitoring notification channel |
| Protected Terraform state | backend configuration | Remote state bucket with versioning; owner-only access |
| Validation window | — | Start/stop times and expected cost (Armor/LB hourly charges) |

## Pre-deployment checklist (offline, safe now)

1. Backend regression, frontend tests and browser acceptance pass on the commit
   to be deployed (`docs/TESTING.md`); record results in `docs/INTEGRATION_RESULTS.md`.
2. Scanner acceptance passes on the exact scanner image
   (`docker run --rm --network none <image> python check_scanner.py`); record engine
   load time and per-scan latency.
3. Re-scan the exact backend, scanner and frontend images for native
   vulnerabilities; triage any new Critical/High per `docs/NATIVE_DEPENDENCY_RISK.md`.
4. `terraform fmt -check` and `terraform validate` on `infra/google/runtime`; run the
   mocked deployment-hold plan tests in `infra/google/runtime/tests`.
5. Reconcile Terraform state ownership: the foundation script owns pre-existing
   Firestore, bucket, dataset, registry and budgets; runtime Terraform imports only
   the existing Tasks queue. Never recreate existing resources.

## Redeploying a change

1. Run the offline checks above, then build and push the changed image(s):
   `docker build -f Dockerfile.cloud -t <registry>/backend:<tag> .` (scanner:
   `Dockerfile.scanner`; frontend: `frontend/Dockerfile` with
   `--build-arg FRONTEND_PROFILE=cloud --build-arg STAFF_ACCESS=practice`), then `docker push`.
2. Put the pushed digest (`gcloud artifacts docker images describe ... --format='value(image_summary.digest)'`)
   into `staging.tfvars`.
3. `terraform plan -var-file=staging.tfvars -out=staging.plan`, review that nothing is
   destroyed, then `terraform apply staging.plan`.
4. Run `python scripts/cloud_staging_check.py https://8-233-217-230.sslip.io`.

`infra/google/cloudbuild.yaml` remains available to build and test in Cloud Build instead
of locally.

## Staging acceptance (after deployment)

- Real IAM: each service identity can reach only its dependencies; direct API
  ingress bypassing the load balancer is refused.
- Firestore contention on concurrent approvals/jobs; Cloud Tasks retry recovery.
- BigQuery publication and replay; WAF behavior on multipart uploads.
- A fresh complaint through real Document AI and Vertex AI to both simulator
  receipts, plus the retained unfamiliar inputs (N28 and the manual O/0 receipt).
- Staff Google sign-in with mapped and unmapped subjects.

## Rollback

Set `dispatch_enabled = false` (pauses Tasks/Scheduler), then scale services to
zero or roll Cloud Run traffic to the previous revision. Evidence buckets and
Firestore have deletion protection; do not destroy them during rollback.
