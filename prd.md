---
doc: prd
status: implemented-prototype
---
# CaseProof — Product Requirements

This is the current product contract for the incorporated and locally verified CaseProof prototype. See [scope.md](scope.md), [spec.md](spec.md), [verification](docs/SUBMISSION_VERIFICATION.md) and [source provenance](SOURCE_PROVENANCE.md). Implementation verification is distinct from competition eligibility or production readiness.

## The Core Journey
1. Landing explains the analyst's problem, shows the output and offers reporting, analyst demo and guided tour entry.
2. Start a fresh practice session with fictional bank data and no complaints; select a customer and a supported payment-age scenario.
3. Select disputed payments, describe the incident, optionally supply first-contact time, attach supported evidence and review before submitting.
4. Receive a persistent acknowledgement; a clearly labelled demo handoff directs the tester to the analyst role without confusing the customer service itself.
5. The analyst queue receives the new case and a single arrival alert. Golden-hour priority comes from authoritative bank payment timestamps.
6. Overview presents response window, recommended action, confirmed amount, additional candidate, supported findings and unresolved questions together.
7. Inspect original evidence and extracted detail; follow the account graph and inspect transfer sources and observation times.
8. Send a justified proposed missing-information request where needed. The customer uses the scoped reply link; new evidence triggers reassessment.
9. Explicitly confirm or exclude any additional debit; never treat a candidate as disputed by default.
10. When supported, visibly hand off to reviewer. Reviewer checks the current version, writes a reason and approves that exact snapshot. Urgent referral has separate eligibility and limited scope.
11. Send the approved packet; show both actual synthetic receiver acknowledgements and the delivered report, including traced movements and source references.
12. Assign owner and next action; preserve awaiting-external follow-up, history and reload persistence. Repeat with another new case.

## Screens and Layout
- Landing: established visual identity, product explanation, visible tour entry and favicon.
- Victim: responsive account selection, four-step report wizard, confirmation/status and capability-bound reply screen. No staff-only controls except explicitly labelled practice handoff.
- Queue: actionable prioritised work; Cases: browse case history/status. The two destinations must not merely rename the same unaltered screen.
- Case workspace: Overview, Evidence, Money Trail, Requests, Review & decision, Delivery & follow-up, Audit.
- Overview: compact top response-window and next-action row, balanced brief/payment columns and optional AI tools below essential work. Avoid empty stretched columns and excessive scrolling.
- Evidence: original and source-linked extracted details; understandable status and citation navigation.
- Requests: current recommendation and rationale first; proposed, sent, answered and suppressed history clearly separated.
- Review: readiness, outstanding gaps, role explanation and explicit reviewer action.
- Delivery: two destinations, immutable packet history, readable report and owner/next action.

## Look and Feel
Match current redesigned CaseProof and the supplied money-trail reference. Preserve typography character, palette, controls and density through measured comparison. No generic replacement dashboard. Avoid oversized next-action banners, truncated persona controls, nested search borders and offscreen tour buttons. Victim mobile/tablet and analyst laptop/desktop are required. Keyboard focus, readable contrast and reduced-motion handling are part of quality.

## Features and Behavior

### Practice and reporting
- Generate server-backed fictional customer/payment/network records, not browser-created financial conclusions. All supported customers must produce coherent scenarios.
- Sort payments predictably; explain incompatible first-contact/payment timing without silently altering input.
- Accept supported screenshots, receipts, chat and call-log evidence with declared type/size/count limits. Do not promise PDF support without implementing it.
- Practice sample actions show loading only on the clicked sample type, prevent duplicates and disclose whether generation is AI or deterministic in the actual provider mode.
- Stable same-body submission retry creates one complaint; a genuinely new complaint gets a new submission identity.

### Analyst investigation
- Queue polling updates real jobs/workflows with bounded backoff. Role changes do not create duplicate notifications.
- Golden-hour urgency is response priority; elapsed window does not imply futility or a legal recovery deadline.
- Claims distinguish customer statements, extracted observations and bank confirmation. Every visible citation opens its actual source.
- AI assistance explains evidence; server code owns amounts, allocations, readiness and request ranking. Citation/number checks must not be described as complete semantic verification.
- Live Money Trail uses actual case graph data: account cards, hop columns, transfer amount/time labels, bank-source distinction, selected-debit filter, account inspection, fit/zoom/fullscreen and timeline replay. Missing observations are visible gaps, not invented paths. Replay does not fabricate historical balances.

### Clarification, approval and delivery
- Ask only unresolved relevant questions; no secrets or bank-known facts. Expired/wrong-scope reply links fail safely.
- Analyst can investigate and request information but cannot approve reviewer-only actions. Both roles can read shared evidence to understand the decision; mutation permissions remain server-enforced.
- An urgent referral is a limited supported transaction referral, not permission to present an incomplete investigation as complete.
- Approval requires current revision, digest, disposition and reason. New financial content invalidates use of old approval for a new packet.
- Queued send is not delivery. One receiver acknowledgement is partial delivery. Both acknowledgements complete the handoff, while the investigation remains open.
- Report contains supported narrative, payments, unresolved matters where applicable, money trace, sources, approval and observation limits. Printable/readable output is mandatory.

### Guided tour
- Short, high-impact, role-aware journey with real user actions, loading feedback, bounded waits and retry guidance.
- Starting or restarting must produce a coherent entry state; no stale step masquerades as a fresh session. Fresh-session creation is explicit.
- Resolve targets after actual readiness; never advance into missing screens. Minimise/close and action buttons remain reachable at small heights.

## States and Boundaries
- Empty practice: prepared data, zero complaints, useful reporting CTA; no fabricated metrics.
- Processing: upload received, scan and extraction still pending; show actual status and supported retry.
- Invalid/failed evidence: preserve original, explain rejection, allow supported recovery.
- Provider unavailable: visible failure/unavailable state, never fabricated Gemini output.
- Stale approval or assignment: reload current state and require a fresh deliberate action.
- Access denied: preserve role/tenant/capability isolation; no client-side role assignment in production auth.
- Persistence: original artifacts, revisions, approvals, delivered packets, audit and ownership survive reload.

## Product Decisions
Established learner priorities: full connected journey; analyst as primary user; source-linked brief and justified first action as outputs; preserve current visual quality; real backend behavior; clear synthetic disclosure; no automatic recovery claims. Fast batched planning was explicitly requested. The current release publishes this package to the submission repository and restores the existing demonstration services. Publishing source is not submission of the competition entry.

## What We're Building
The connected surfaces and acceptance journey above, with real persistence and processing. Completion requires UI/backend tests, reference comparison, a readable handoff, tour checks and learner review; successful compilation alone is insufficient.

## Deferred From the POC
Production bank connectivity, real money movement, live production staff authentication validation and institutional compliance approval. These cannot be established by a synthetic demo.

## Possible Later Enhancements
Practitioner-led workflow evaluation and measured time-to-supported-action, clarification rounds and reviewer rework.

## Non-Goals
No hidden dataset editing by normal testers, guaranteed recovery, universal financial advice, autonomous authorisation, invented testimonials or retrospective development records.

## Remaining validation and launch work
- Final human review of the narration, captions and public video upload.
- Confirm public cloud access and live provider behavior after service restoration; the local video uses the separately documented Gemini Developer API profile.
- Production staff authentication and real banking/receiver integrations remain outside the practice prototype.
- Measure usability and time-to-supported-action with real analysts before making benefit claims.
- Event eligibility, required entry fields and any curriculum review remain separate from technical test results; no retrospective approvals are asserted.
