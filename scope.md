---
doc: scope
status: implemented-prototype
---
# CaseProof — Scope

**A justified first response to a payment scam.** CaseProof helps a bank's payment-scam response analyst turn a customer report, original evidence and bank records into a source-linked investigation brief and a separately reviewed handoff.

## Users and problem
The analyst must reconcile fragmented receipts, messages and bank records, distinguish disputed payments from unrelated debits, identify consequential gaps and justify the first action. The customer supplies the report and clarification. The reviewer authorises the supported report independently. Practitioner-measured time savings have not been established.

## Core loop
Report → prioritise → inspect sources and money movements → clarify → review the current version → deliver → retain follow-up ownership.

The golden hour is a response-priority window calculated from bank payment time. It is not a guarantee of fund availability or recovery.

## Included in the prototype
- Landing page and guided demo with fresh, server-generated fictional bank data and no account-registration requirement in practice mode.
- Responsive victim reporting, supported evidence uploads, receipt/chat/call-log practice samples, status and scoped customer replies.
- Analyst queue and case history, deduplicated arrival alerts, response window, investigation brief, inspectable citations, bank matches and interactive Money Trail.
- Focused missing-information requests, explicit additional-payment decisions and reassessment.
- Reviewer-only, revision-and-digest-bound approval; separately assessed urgent referral.
- Durable delivery to two synthetic receivers, a readable investigation report with traced movements, audit and persistent ownership/next action.
- Real local processing and optional live Gemini processing; a separate Google Cloud runtime uses its configured cloud adapters.

## What working means
A new complaint—not a pre-completed case—reaches actual evidence processing, source inspection, customer clarification where needed, accurate disputed-payment selection, independent approval, both receiver acknowledgements and a readable report. Reloading preserves the handoff and follow-up. The local acceptance repeats the journey with a second new complaint.

## Design
Warm ivory surfaces, white bordered cards, indigo actions, restrained amber urgency, editorial typography and a source-backed account graph. Victim reporting is calm and guided; staff investigation is compact and operational. The demo uses the implemented interface rather than invented product slides.

## Boundaries
Bank records, onward observations and receiver acknowledgements are fictional runtime data. No real freeze, refund, regulatory filing or investigation closure is performed. AI assists evidence interpretation; server rules own financial calculations/readiness, and a reviewer authorises delivery. Production identity, bank integrations, compliance and practitioner benefit measurements remain future work.

## Implementation and evidence
The team-owned CaseProof source was incorporated with the provenance recorded in [SOURCE_PROVENANCE.md](SOURCE_PROVENANCE.md), then repaired and verified in this package. These current planning documents describe the implementation; they do not manufacture a historical sequence of curriculum approvals. See [prd.md](prd.md), [spec.md](spec.md), [verification](docs/SUBMISSION_VERIFICATION.md) and the [demo guide](LOCAL_DEMO_GUIDE.md).
