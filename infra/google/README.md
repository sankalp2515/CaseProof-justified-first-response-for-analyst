# Google runtime infrastructure

Project `caseproof-511713`, Mumbai `asia-south1`. Staging is deployed (see
[deployment record](../../docs/DEPLOYMENT.md)); defaults still fail the deployment gate,
so applying requires the explicit staging variables.

## Components

| Selected capability | Implementation |
| --- | --- |
| Cloud Run | Frontend (nginx, `frontend/Dockerfile` with `FRONTEND_PROFILE=cloud`), API, private worker, private simulator, private scanner |
| Vertex AI Gemini | Existing ADC transport; structured extraction; shared call limits; deterministic validation |
| Document AI | Pinned regional processor/version, original line anchors and boxes, confidence downgrade, explicit failures |
| Cloud Storage | Private quarantine -> clean evidence after matching clean scan; immutable exported packet objects |
| Firestore Native | Cases, append-only revisions/approvals/audit, sessions, leases, ownership, task/outbound intents |
| BigQuery | Parameterized tenant/as-of bank, coverage, complaint-link and downstream queries; byte/result limits |
| Cloud Tasks | OIDC commands for scan, process, bank publication and delivery; durable publication/recovery |
| Cloud Scheduler | Private reconciliation, clock transitions and synthetic observation refresh; initially paused |
| Artifact Registry | Existing registry; digest-pinned images; manual Cloud Build test/build configuration |
| IAM | Attached per-service identities, staff subject-to-role mapping, exact service identity checks |
| Logging/Monitoring | Route-template structured events, queue delay and error metrics/alerts; raw URL logs excluded |
| Budget/resource controls | Existing foundation budgets plus daily/per-case model caps, query bytes, case/instance/concurrency limits |
| Cloud Armor Standard | HTTPS load balancer, victim request throttle, WAF preview, direct API ingress restriction |

Secret Manager stays conditional: no external password or service-account key is
needed by this ADC-based prototype. Cloud Armor is not malware scanning: the
private ClamAV service gates quarantine promotion and OCR. Scanning fails closed
when unavailable or signatures are older than 72 hours. Evidence remains restricted
to existing PNG/JPEG/text limits; no PDF coverage claim.

## Offline checks (safe to run)

`Dockerfile.cloud` is the prepared Google runtime (pinned Trixie, no local OCR
binary or evaluation fixtures). `Dockerfile` retains the local OCR regression
environment. The manual Cloud Build configuration tests both before publishing
backend/scanner images; it contains no deploy step. Do not execute Cloud Build
while the deployment/build-publication hold applies. Scanner upgrade, native
advisory findings and release boundaries are in [security](../../docs/SECURITY.md)
and [validation](../../docs/TESTING.md).

```powershell
var/tools/terraform/terraform.exe -chdir=infra/google/runtime fmt -check
var/tools/terraform/terraform.exe -chdir=infra/google/runtime validate
```

`validate` checks provider schema/configuration; it does not verify deployed IAM,
regional quotas, CEL rule acceptance, actual model accuracy, or connectivity.
`.terraform.lock.hcl` pins the provider; state, tfvars, local evidence and credentials
are excluded from Docker/Cloud Build source. No credentials belong in images.

The foundation script owns the existing default Firestore database, evidence
bucket, dataset, registry and billing controls. Runtime Terraform owns new services,
IAM members, tables, quarantine, edge and alerts. An explicit import block adopts
only the pre-existing Tasks queue. Reconcile state ownership and use a protected
remote Terraform state before any later apply. Do not recreate existing resources.

## Frontend contract handoff

- Cloud staff requests need `Authorization: Bearer <Google ID token>` with the
  configured OAuth client audience and a server-mapped Google subject. Local demo
  role headers are not cloud authorization. The cloud frontend build signs staff in
  with Google Identity Services using `VITE_GOOGLE_CLIENT_ID` (Cloud Build
  `_STAFF_CLIENT_ID`); real sign-in is unverified until staging.
- Victims use secure HTTP-only same-site cookies. All browser requests must use the
  same public HTTPS origin; deploy the frontend through the same load balancer.
- An administrator explicitly invokes `POST /v1/admin/synthetic/preload` once.
  It creates bank records, not cases. Jobs publish records asynchronously; victim
  endpoints may return `503 bank_data_preparing` with a retry hint. No import-time seed.
- `POST /v1/victim/demo-session` creates a fresh isolated synthetic session with
  preloaded records. Cases are created only by real complaint submissions.
- Upload returns before quarantine scanning and extraction complete. Poll jobs/case;
  retain pending/error states. Never show a pending scan as extracted evidence.
- Requests use the existing customer capability-link endpoints; approval requires
  exact current revision and digest. Reviewer and analyst roles remain distinct.
- Export returns queued delivery intent. Show delivered only after both simulator
  receipts exist; delivery leads to `awaiting_external`, not investigation closure.
- Background reconciliation refreshes independent synthetic observations. Victims
  and analysts do not need to open a simulator to refresh data.
- `POST /v1/admin/synthetic/networks/{network_id}/refresh` is an administrative
  evaluation hook, not a normal victim or analyst step.

Keep the current local Docker environment available. Cloud mode never silently
falls back to SQLite, DuckDB, local OCR, mock model responses or real bank delivery.
Production configuration is deliberately rejected until institutional adapters and
controls exist. Cloud simulators are explicitly synthetic, privately authenticated
receipt sinks; they do not freeze funds or file official reports.

## Gates before a later deployment

1. Frontend/cloud API authentication and asynchronous-state acceptance.
2. Verified processor/version and Gemini availability/quotas in Mumbai, using tiny
   paid smoke tests only when authorized; evaluate retained unfamiliar pixels.
3. Dedicated staff mapping/OAuth audience, real domain, alert email and image digests.
4. Existing-resource/state import review, billable resource estimate and test window.
5. Apply only after the user's deployment instruction; queues and Scheduler remain
   paused until service/IAM/negative-auth smoke tests pass.
6. Test real Firestore conflicts, BigQuery publication replay, Tasks retry recovery,
   Cloud Armor ingress bypass and WAF multipart false positives in the deployed setup.
7. Full new complaint through actual Document AI/Vertex to simulator receipts;
   no synthetic provider response may count as live AI quality evidence.

## Cost gate

The $25 initial budget is a planning limit, not an automatic billing stop. The edge
has hourly charges even without requests. At published USD list rates, one Standard
policy and three rules are approximately $8 per 730-hour month, before the HTTPS
load balancer, address/traffic, scanner compute, model/OCR and other services.
A full-month edge plus backend cannot be promised within $25. Use a short planned
validation/demo window and a fresh estimate before deploying. Budgets notify;
application limits reduce usage but do not guarantee an account-wide spending cap.
No Enterprise subscription or hierarchical security policy is configured.

Official references checked 17 October 2026:
- https://cloud.google.com/armor/pricing
- https://cloud.google.com/load-balancing/pricing
- https://docs.cloud.google.com/document-ai/docs/regions
- https://docs.cloud.google.com/document-ai/docs/processors-list
