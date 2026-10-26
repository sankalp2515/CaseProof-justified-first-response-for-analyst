---
doc: spec
status: implemented-prototype
---
# CaseProof — Technical Spec

## How This Works, In Plain Language
The browser presents reports and investigation work. An API validates identities and actions, persists the case and queues processing. A worker scans/reads evidence, checks it against bank records and computes an assessment. AI drafts assistance from cited material; it does not authorise actions or determine financial totals. Separate synthetic institutions supply bank observations and acknowledge exported reports. The reviewer approves the exact snapshot delivered.

This architecture describes the existing application incorporated into this folder from the source revision recorded in SOURCE_PROVENANCE.md, with subsequent local integration repairs. Runtime isolation is implemented through the caseproof-devpost-local Compose project and loopback port 8246. The default profile uses local OCR/extraction; the opt-in compose.gemini.yaml profile was tested with real Gemini image reading, extraction and cited summary. Bank records, feeds and receivers remain synthetic. See PACKAGE_READINESS.md for test evidence, provider failures and public-access blockers. This document describes current implementation, not a retrospective sequence of curriculum approvals.

## The Core Journey Through the System
PRD ref: prd.md > The Core Journey.
1. Session service creates an isolated fictional practice catalogue and HTTP-only customer session.
2. Reporting UI sends account-bound selected payments, narrative and stable submission ID to the API; multipart uploads include file and kind without a manual boundary.
3. Durable processing intents run scan/OCR/extraction and bank matching. Original content and source locations remain inspectable.
4. Server assessment creates a revision/digest, supported payments, candidate decisions, graph, readiness, priority and proposed requests.
5. Staff client polls authoritative workflow/jobs and deduplicates notifications using stable case/event identifiers, independently of persona changes.
6. Request service issues an expiring bound reply capability; submitted replies trigger new processing and preserve original evidence.
7. Reviewer action includes expected revision/digest/disposition/reason; the API validates role, freshness and eligibility atomically.
8. Durable idempotent delivery sends the approved snapshot to both synthetic receivers. Follow-up has its own assignment version/history.

## Stack
- React 18 / Vite browser application. Exact resolved versions are in frontend/package-lock.json.
- Python / FastAPI API, durable worker and domain model. Dependencies are pinned in requirements.lock.txt and requirements-scanner.lock.txt.
- Default local profile: SQLite, DuckDB, local object storage, Tesseract OCR and explicit extraction rules.
- Opt-in local live profile: Gemini Developer API, gemini-3.1-flash-lite, image OCR/extraction and cited summary; fallback disabled, 8 calls per case and 100 daily calls. Server-side key only.
- Google Cloud runtime: Cloud Run, Firestore, Cloud Storage, BigQuery, Cloud Tasks, Scheduler, Document AI OCR and Vertex Gemini. Actual cloud provider configuration and source-image parity must be checked independently of local tests.
- Vitest/component tests, pytest, Playwright and axe provide automated verification.

## Where It Runs and How Someone Tries It
From a fresh checkout, run `docker compose up --build -d --wait` and open http://127.0.0.1:8246/ . The Compose project is caseproof-devpost-local with isolated volumes and a loopback-bound frontend. No cloud credentials are needed for the default profile.

For live Gemini, put GEMINI_API_KEY in ignored .env and run `docker compose -f compose.yaml -f compose.gemini.yaml up --build -d --wait`. See [LOCAL_DEMO_GUIDE.md](LOCAL_DEMO_GUIDE.md). Never commit credentials, browser sessions, customer reply capabilities or runtime databases.

The existing public cloud origin is https://8-233-217-230.sslip.io . Its restoration and actual public acceptance are recorded separately in [verification](docs/SUBMISSION_VERIFICATION.md). Cloud and local images are not assumed identical. No Terraform apply or image redeployment is needed merely to restore the stopped services.

## Look and Feel
PRD ref: prd.md > Look and Feel, Screens and Layout.
Extract and measure reference palette, typefaces, spacing, borders, card radii, density and control states before building visible components. Treat existing screenshots and source as disclosed reference material, not fresh authored work. Define semantic tokens and reproduce essential alignment at 390x844, 768x1024, 1242x668 and 1920x1080; these are proposed verification sizes.

Use a compact fixed staff header, reachable role selector, top response-window/next-action row, balanced case content and horizontally scrollable graph/table containers where necessary. Avoid whole-page horizontal overflow. Graph animation must respect reduced motion. Fullscreen must be tested both in the browser and in the actual video capture; correct screenshots alone are insufficient.

## Components
### Browser application
PRD refs: Screens and Layout; Guided tour. Route-level landing, victim wizard/status/reply, staff queue/cases, case workspace and delivered document. One API/state layer handles credentials, cancellation, bounded polling and both `detail` and `error` envelopes. Do not call private `/internal` worker routes from the browser.

### Workflow API and authorization
PRD refs: Practice and reporting; Clarification, approval and delivery. Tenant/account-bound reads/mutations, idempotent intake, source access, exact-version approval and immutable exported content. Local demo uses labelled supported personas. Production bearer identity, if later enabled, is verified server-side; browser never chooses production roles. Victim cookies use same-origin routing and credentials inclusion; no wildcard credentialed CORS or disabled Origin checks.

### Processing and assessment
PRD refs: Analyst investigation; States and Boundaries. Scan immutable evidence, run configured OCR/AI, retain source coordinates/quotes, compute money/readiness/request ranking server-side. Unknowns persist when evidence is insufficient. Provider labels must match actual execution. Source filtering validates citations/numbers only unless stronger entailment verification is actually implemented and evaluated.

### Bank network and graph
PRD ref: Analyst investigation. Synthetic records are independent inputs. Maintain conservation/accounting invariants for each supported payment, explicit observation timestamps and unaccounted/cash-out states. Client positions nodes and animates server-provided transfers; it does not calculate financial allocation. A second fresh catalogue tests generality beyond a canned case.

### Requests, review and delivery
PRD ref: Clarification, approval and delivery. Server-issued scoped links preserve bindings through upload/complete. Request generation avoids settled facts. Reviewer checks are independent of ordinary staff navigation. Outbound intents are retryable and receiver-idempotent; report and history preserve the approved version even after later assessment.

## Data Model
- PracticeSession: tenant, fictional catalogue, selected customer, creation/expiry. Customer session cookie is HTTP-only.
- Complaint: case ID, account, submission ID/body identity, narrative, selected transaction IDs, creation timestamp.
- Artifact/Segment/Claim: immutable original hash, kind, scan/provider state, quoted source and location, reported/extracted/bank-confirmed distinction.
- Snapshot: monotonic revision, financial digest, payment inventory, candidate decisions, graph, observation freshness, readiness, urgent eligibility, proposed requests.
- Job: kind, case/revision binding, queued/running/succeeded/failed state, attempts and retry eligibility.
- Request/Reply: catalogue proposal, state, scope bindings, capability expiry, uploaded artifacts and completion.
- Approval: actor, role, revision, digest, disposition, reason and timestamp. Never silently updates with a new snapshot.
- Delivery: immutable approved packet, destination, stable idempotency key, attempts and acknowledgement.
- FollowUp/Audit: owner, next action, due date, awaiting-external state, assignment version and append-only history.

## File Structure
```text
frontend/              React/Vite views, API/state, design, graph, tour and browser tests
caseproof/             FastAPI, domain assessment, authorization, jobs and storage adapters
local_services/        OCR and local runtime support
mock_services/         Synthetic receivers and supporting practice services
tests/                 Unit, flow, provider and domain regression tests
compose.yaml           Isolated default local runtime
compose.gemini.yaml    Opt-in live Gemini profile
infra/google/          Explicit Google Cloud adapters and infrastructure configuration
scope.md/prd.md/spec.md Current product and technical contracts
devpost/               Skill Pack planning entry points and verification checklist
var/                   Ignored runtime evidence, private sessions and recordings
```

## External Services and Dependencies
API contract: [docs/API_WORKFLOW_CONTRACT.md](docs/API_WORKFLOW_CONTRACT.md). Running OpenAPI and real browser/API acceptance were used to verify the local integration. Cloud acceptance is tracked separately.
- Session/account: demo-session, demo-customers, session creation and victim me.
- Intake: complaint creation; multipart evidence; explicit additional-payment decisions.
- Staff: workspace, current snapshot, workflow, brief/report preview, job and supported retry.
- Clarification: request/send and capability-bound reply/upload/complete.
- Review/output: expected-revision/digest approval, export, approval/audit/packet history and follow-up.
- Google, if separately authorised: Document AI OCR and Vertex Gemini. Tokens/keys remain server-side, no credentials in URLs/logs/localStorage. Model, quotas, availability and costs require fresh verification before activation. Documentation: https://cloud.google.com/document-ai/docs and https://cloud.google.com/vertex-ai/generative-ai/docs .

## Important Failure Modes
- Invalid/unscannable evidence or provider outage: retain original and explicit failed/pending status; offer only supported retry, no fake extraction.
- Stale data/version during review: server rejects conflict; reload and require deliberate fresh review rather than reuse old approval.
- Expired capability, wrong account or denied role: explain unavailable/access denied without cross-tenant disclosure.
- Partial delivery: retain one acknowledgement and retry only outstanding work; no premature completed claim.
- Tour target/provider delay: loading/minimise/retry remains accessible; step does not advance into a missing panel.

## What Was Simplified and Why
Fictional bank institutions and synthetic receivers substitute for integrations requiring institutional authority. They supply real runtime inputs/acknowledgements, not fixed successful API responses. Production identity and real fund actions remain outside the prototype. No learner-approved reduction of the requested full journey has occurred.

## Decisions and Open Issues
- Full journey and existing visual quality: explicitly requested by learner.
- Fast batched preparation: explicitly requested; does not approve unseen plans or waive verification.
- Prior source integration is documented; the local default and live Gemini profiles are implemented and verified. Cloud image parity is a separate release check.
- AI citation and numeric consistency checks do not establish semantic truth. The UI explicitly retains analyst review, and recovery claims remain unsupported.
- Competition eligibility remains unresolved. No fabricated provenance or backdated checkpoints.

## Verification Strategy
Test new reports from two fresh catalogues, supported evidence, queue arrival without duplicate role-switch alerts, real worker results, exact citation selection, graph source/accounting, actual request reply/new revision, explicit debit exclusion, analyst approval denial, current reviewer approval, both acknowledgements, delivered money trace and persisted follow-up. Inject stale revisions and receiver/provider failures. Compare reference screenshots, check keyboard/focus/contrast/overflow with Playwright and axe, inspect actual video frames and report limitations honestly.
