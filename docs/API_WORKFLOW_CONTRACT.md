# Local backend workflow contract

**Updated: 17 October 2026.** This documents the shared frontend/backend workflow.
Local demonstration roles are distinct from prepared cloud staff authentication. OpenAPI at
`/openapi.json` defines request shapes. The rules below define cross-endpoint
meaning that OpenAPI alone does not express.

## Read surfaces

| Surface | Meaning |
| --- | --- |
| `GET /v1/victim/me` | Only the signed-in synthetic account's payments and complaint references |
| `GET /v1/cases/{id}` | Current financial snapshot; revision, digest, sources, claims, readiness, requests, trail |
| `GET /v1/cases/{id}/workflow` | Current job, approval, delivery, follow-up and attention state; current display time can make observations stale |
| `GET /v1/jobs/{id}` | Durable job status/error plus enqueue/start/finish times and attempt count; historical timing can be null |
| `GET /v1/cases/{id}/audit` | Revision/event chronology; not permission to mutate history |
| `GET /v1/cases/{id}/approvals` | All past approvals, not only the current eligible approval |
| `GET /v1/cases/{id}/delivered-packets/{packet}` | Immutable delivered content for that case; may be historical |

## Workflow status vocabulary

| Wire status | Display meaning / next step |
| --- | --- |
| `new` | No evidence; receive evidence or inspect intake |
| `processing` | Current revision queued/running; wait/poll, no claim of completed assessment |
| `failed` | Explicit current provider/job failure; inspect error and retry only if current |
| `needs_analysis` | Evidence not yet assessed at the current revision |
| `needs_attention` | Stale observations or delivery problem; internal refresh/recovery before unsupported send |
| `awaiting_information` | A request was sent/accepted; await response or record unavailability |
| `ready_for_review` | Deterministic readiness permits human review; not authorisation |
| `approved` | Current financial revision/digest approved; destination delivery may still be pending |
| `completed` | Both full-report destinations acknowledged the approved packet; **delivery complete, investigation remains open** |

Do not infer action permission from status alone. Full readiness, urgent eligibility,
actor role, source freshness and exact revision/digest are separate authoritative
checks. An urgent referral can be supported while complete documentation is not.
`followup.state` remains `open` or `awaiting_external`, with owner/next action/due;
there is no investigation-closure or funds-recovered claim in this contract.

## Mutation and recovery rules

| Action | Required invariant | Failure / recovery |
| --- | --- | --- |
| Submit complaint | Own-account transactions; stable submission ID and identical body | Same-body replay returns same case; changed body conflicts; submit is intake, not completed OCR |
| Upload evidence | Owned case, allowed kind/type/size; content-addressed immutable original | New revision with atomic processing intent; original approval/history retained |
| Answer payment question | Own account; explicit disputed/denied decision | Candidate is not loss until confirmed; bank-only gaps are internal |
| Send request | Current catalogue proposal and permitted content | No OTP/PIN/password or request for information already settled by the bank |
| Retry failed job | Failed job still at current case revision | 409 on obsolete jobs; inspect new current revision instead of replaying old work |
| Correct evidence | Current revision and quoted source; retain original | Source validation still applies; correction does not overwrite original evidence |
| Approve full/urgent | Reviewer role, supported eligibility, rationale, revision/digest | Stale/changed approvals cannot authorise new content |
| Export | Exact approved financial content, current eligibility/freshness | Durable outbound intents and stable receiver keys; outage is pending/retry/failure, never simulated success |
| Assign follow-up | Current financial revision plus assignment version | Stale revision/version conflicts; append ownership history |

`403` means denied role/tenant/capability. `404` means unavailable resource.
`409` returns `{"error":"<conflict code>"}`; reload current state before retrying.
`422` rejects invalid action/evidence; stale-bank errors identify refresh/reprocess.
FastAPI request-schema failures use its `detail` list; clients must handle both
schema and business-validation errors. OCR is internal: 429 means admission full,
503 means queue/engine failure. Neither response contains fabricated observations.

New evidence/bank updates can change financial revision while a user is reviewing.
Always reload after a conflict; never carry an old digest into a new approval.
Historical packets and approvals are auditable evidence, not a current action.

## Executable coverage

Existing suites cover these contracts: `test_workspace`, `test_victim_flow`,
`test_approval_history`, `test_durable_handoff`, `test_followup`,
`test_freshness_expiry`, `test_job_telemetry`, `test_ocr_capacity` and browser flows.
Accepted HTTP burst samples additionally exercise intake idempotency, actual OCR,
worker publication and current workflow polling under competing work.

Demo role headers/cookies are synthetic access controls. Real SSO, institutional
authority and production tenancy remain outside this local contract.

## Receipt replacement and OCR uncertainty

Readability is checked for each receipt artifact. A supported replacement with the
same payment reference can resolve an unknown amount. An unidentified original
can instead be resolved by one usable receipt uploaded for that original's
fulfilled readability request. The server records `receipt_artifact_ids` and
`replacement_artifact_ids` within the existing request `explanation` dictionary;
clients do not choose these values. Reissued links preserve the same bindings.
Multiple unidentified originals remain unresolved when a reply cannot establish
which original it replaces. Different known references and cross-artifact amount
citations cannot clear the gate. Urgent-referral eligibility remains separate.

The v5 local OCR provider marks repeated low-confidence timestamp observations
with an `:uncertain-timestamp` segment model tag. Their claims remain `reported`,
with an explicit note in structured and readable investigation briefs; they do
not independently satisfy date readiness. Bank timestamps retain their separate
source. No new contract defaults were added, preserving historical snapshot digests.

Historical unidentified receipts without server replacement bindings can reopen a
readability gap when reprocessed. Use a newly scoped request or escalation with
gaps; do not rewrite a historical approval to make an old case appear complete.

A partial receipt with one uniquely corroborated bank reference and no amount
claim does not require resending the bank-known amount. An ambiguous or invalid
amount claim cannot use that shortcut. The original receipt remains partial;
the bank amount keeps its own provenance.

## Scoped clarification return target

`GET /v1/customer/{token}` validates the capability before returning its scoped
`case_id`. The frontend retains that return target after consuming the link;
accessing the report still requires the correct victim session. The local web
host bridges `/customer/{token}` to `/app/#/victim/reply/{token}` only after
validation. Invalid or expired links stay denied and are never generic SPA success.
