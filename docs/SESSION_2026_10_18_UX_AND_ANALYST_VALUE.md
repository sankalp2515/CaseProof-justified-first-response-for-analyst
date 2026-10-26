# CaseProof: 18 October repairs and analyst value walkthrough

## Environment and provider correction

All work is isolated in `codex/landing-demo-journey`, under `C:/Users/sanka/.codex/worktrees/landing-demo-journey/CaseProof`. The main deployment checkout and its services were not edited. Nothing in this session was deployed, merged or pushed.

**Deployed staging uses Google Document AI and Vertex AI Gemini.** The 17 October live acceptance record in `INTEGRATION_RESULTS.md` establishes that fact, including a completed public workflow. A read-only health check on the staging URL returned HTTP 200 and provider `vertex+documentai` during this review. Earlier blanket wording that Google was unverified was incorrect and is superseded. Staff Google sign-in and real institutional bank connections are separate from Gemini evidence processing.

The repeatable repair tests use the isolated local API on 8184, frontend on 8188, actual worker/OCR and simulator receivers. Their provider records describe that particular environment; they do not invalidate deployed Gemini. No live cloud mutation or new Google call was needed for these repairs.

## What changed in this session

| Issue | Cause and repair |
|---|---|
| Popup returned on identity switches | Role/scope changes reset the notification baseline. Replaced that reset with a browser-session ledger of case IDs and read state. |
| Notification count increased without actions | Every status change received a timestamp-based event ID. Routine Processing/Review changes now update the existing complaint facts instead of creating arrivals. |
| Historical scope polluted current alerts | Notifications use the active practice queue independently of the Cases register. Only current practice rows are visible. |
| Open case still appeared unread after loading | Marking read now also follows the actual queue response, including a delayed first response. |
| Two-minute idle reassessment churn | Local simulator success observations refreshed every 120 seconds. They now refresh near the 900-second freshness boundary (840 seconds), with immediate coverage for a new complaint and short retry after a failed refresh. |
| Narrow case heading collapsed into a text column | A hidden avatar left an unused grid column. Mobile case summary and metrics now each use a complete row. |
| Header avatar was absent/misaligned | Grouped avatar and demo identity into a compound control, aligned to the selected role. |
| Requests explanatory text/button touched | Applied explicit body padding and a 14px vertical stack gap to this specific card. Accepted Review rationale padding is preserved. |
| Missing URL logo | Corrected the React favicon URL for `/app/` hosting and added the same favicon to the landing page. |
| No landing-page tour entrance | Added Take the guided tour, directly into the reporting entrance. |
| Broken resume after a failed step | A global Tour launch always starts at the introduction and reporting entrance. It clears the guide's case association, not the bank catalogue/history. Explicit Start a fresh practice session remains the action that creates a newly timed bank world. |
| Hidden restarted guidance | A fresh guide launch remounts its overlay, including after minimising. |
| Premature delay warning | Guidance shows a loader during real page loading, including when the surrounding target card already exists. It waits longer for a busy page and offers Restart guidance on a genuine missing screen. |
| Wrong case selected on chapter jump | Removed fallback selection of the first queue case. Case-specific guidance requires the complaint created/opened in that journey. |
| Unclear urgent-referral action | Added a safe-account example and eligibility explanation inside Review & decision. |
| Overbroad Google disclaimer | Corrected the landing FAQ and appended a dated correction to the previous session guide. |

## Why a case can change while nobody clicks

The worker continues queued extraction, bank-feed ingestion, delivery retries and clock/freshness checks independently of the browser. A completed extraction can legitimately move Processing to Review. A new observation or evidence can create a new revision and invalidate an old approval. Passing a clock/freshness boundary can also require reassessment. These are intentional protections.

The supplied case `CASE-0999285a134ff919` additionally had repeating bank-import, two bank-feed events and a processed event about every two minutes. That unnecessary local simulator cadence was real and is repaired. We did **not** freeze revisions, stop the worker, suppress new external data, or bypass stale-data checks. Later freshness-driven updates remain possible, including after an earlier packet was delivered; the original approved packet remains in history.

## Urgent referral and role boundaries

An urgent referral is a transaction-scoped early alert: the disputed debit is established, while parts of the narrative or downstream investigation may still be incomplete. The server requires at least one matched disputed debit, no material conflicting claim and no unprocessed evidence. A reviewer approves its current revision and digest with a reason. The separate complete-handoff assessment has broader requirements. Neither action establishes a freeze, refund or closed investigation.

| Screen or action | Analyst | Reviewer | Why |
|---|---|---|---|
| Queue and Cases register | Read | Read | Prioritise work and find the exact complaint/history. |
| Overview, cited brief, Evidence, Money Trail | Read | Read | Both must trace the proposed action to supporting facts and limitations. |
| Requests | Read; send clarification and record permitted investigation actions | Read | Reviewer can inspect what was asked and answered without conducting the investigation under that identity. |
| Review & decision | Read; prepare supporting context | Approve the current eligible referral/handoff with reason | Independent authorisation separates investigation from approval. |
| Delivery | Read history and packets | Send the approved packet; urgent-referral sending is also reviewer-only | Dispatch is authorised and auditable. |
| Follow-up ownership | Assign owner/next action | Read | The investigation team retains responsibility after delivery. |
| Audit and approval history | Read | Read | Both need provenance and an immutable record of decisions. |

These are server-enforced permissions. Demo identity lets a judge experience both roles; in an institution they represent separately authorised staff. The current role guide explains this inside the workspace. Cloud staff role discovery/display remains a separate integration consideration; the browser cannot grant permissions.

## The analyst problem: a realistic example, not a pre-solved case

A caller impersonates bank support and persuades a customer to transfer money to a supposed safe account. The customer reports a suspicious debit and attaches a receipt, but does not initially explain how the caller induced the payment. A nearby second debit may be related—or may be ordinary activity. Funds have reportedly moved onward, but observations are time-bound.

The analyst has several real decisions: which payment is actually disputed, whether the receipt matches the bank ledger, what is still unknown, which question could change the next action, whether an early referral is supportable, and what exact content can be approved and sent. A visually complete dashboard alone resolves none of those decisions.

This pattern is grounded in documented impersonation fraud and the movement of proceeds through layered accounts: [official cybercrime advisory](https://cybercrime.gov.in/pdf/Advisories/ADVISORYTAU-ADV-003DigitalArrest06.03.2025.pdf) and [Enforcement Directorate case release](https://enforcementdirectorate.gov.in/sites/default/files/latestnews/Press%20Release-Digital%20Arrest%20Scam%20Case%20-%2027.01.2025%201.pdf). The practice example is fictional and is not a reconstruction of those particular victims.

### Actual completed example from this session

Case `CASE-79f16b3fd0ae1ac8` was newly submitted through the UI with a real PNG receipt. The server matched its ₹51,000 debit, requested missing information, accepted a scoped customer reply, and recorded the extra debit as unrelated. Reviewer approval and both receiver acknowledgements were recorded against revision 14. The investigation team saved owner **Cedar fraud follow-up**, next action **Track receiving institution responses to the delivered packet**, and state **awaiting_external**. Later case revisions may change; the historical packet remains the exact original output.

[Open the actual investigation](http://caseproof-journey.localhost:8188/app/#/staff/cases/CASE-79f16b3fd0ae1ac8/overview) · [Open its delivery/history](http://caseproof-journey.localhost:8188/app/#/staff/cases/CASE-79f16b3fd0ae1ac8/delivery)

The output is an evidence-linked brief plus the approved handoff packet, sourced trail positions/paths, receiver receipts and an accountable follow-up—not a promise to recover ₹51,000. The document preserves the delivered revision/digest. The workspace supplies the interactive graph; the printable handoff includes sourced trail tables and paths.

### Reusable start-to-finish demonstration

1. Open the landing page and choose **Take the guided tour**. Click Next, then **Start a fresh practice session** to obtain a current clock and an empty complaint queue. Choose Samer or another customer; amounts vary by session.
2. Continue to the account, choose **Report a payment scam**, and select the relevant recent unfamiliar debit. Do not select the grocery payment merely because it is nearby. Leave unknown contact time blank; it does not determine the golden hour.
3. Initially report only what the customer knows, for example “I am reporting a suspicious transfer and need the fraud desk to check what happened.” Leave the payment-authorisation answer unknown if it is genuinely unknown. This makes the missing-information problem visible rather than pre-filling a solved case.
4. Download the selected payment's bank receipt and upload the actual PNG. Alternatively attach supported original evidence. Samples are labelled and do not create bank transactions. Review and submit.
5. Use **Continue as analyst demo**. An already open queue receives the new-complaint alert automatically. In Overview, distinguish customer statements from the ledger-supported debit and inspect **Next best step**. Golden-hour priority comes from the server's bank timestamps.
6. In **Evidence**, inspect the receipt and cited extraction. In **Money Trail**, follow the selected debit and inspect sources, observation time and unknown availability. The trail exists because the independent synthetic bank network has records; the browser does not invent flows from the story.
7. In **Requests**, review/send the actual proposed missing-information question. Open its scoped reply screen. A suitable truthful reply for this fictional scenario is “A caller impersonated bank support and told me to transfer money for account verification. I was deceived and followed the instruction.” Submit and wait for the new assessment revision.
8. Return to the customer's report and explicitly confirm or deny the additional debit. For the scenario above, deny it if it was unrelated. Back in the analyst brief, verify that the disputed inventory and next action changed accordingly.
9. Inspect **Review & decision** as Analyst. Approval controls must be disabled. Inspect urgent-referral eligibility separately from complete-handoff readiness; expand **When would I use this?** for the example.
10. Switch the labelled demo identity to **Reviewer**. Inspect the sources and current revision, enter a supported rationale, review and approve the eligible handoff. If the case changed, reload/review; never reuse a prior approval.
11. In **Delivery & follow-up**, review/send the approved reports. Wait for **both** receiver acknowledgements. Switch back to Analyst and save the follow-up owner, next action and assignment reason, retaining **awaiting_external**.
12. Download the original handoff document and inspect Audit/approval history. Reload to verify persistence. Repeat with another customer/new complaint; do not copy a previous fixed account, amount, case ID or digest.

## Product judgement and remaining limits

There is evidence of a real analyst problem and a working decision workflow; there is no basis to conclude that the team has built a completely wrong problem. However, a preloaded, fully explained example can hide that value. Demonstrate the unresolved facts and the change after the analyst's question, not only the final dashboard.

The honest pitch is **a justified first response with traceable evidence and accountable handoff**. It is not universal autonomous fraud investigation, guaranteed tracing across arbitrary banks or guaranteed recovery. Unfamiliar evidence, conflicting accounts, missing bank coverage and partial delivery must remain explicit rather than forced into a successful result. Competition outcomes cannot be inferred from local tests.

Production readiness still requires operational acceptance with target analysts, performance and concurrency testing, representative unfamiliar evidence, accessibility review beyond sampled automated scans, institution-specific bank interfaces and authorised staff identity acceptance. These are separate from the already demonstrated live Gemini processing.

## Evidence

Before/after mobile-header and Requests screenshots, tour-loading/footer captures, the generated handoff HTML/PDF, output verification and regression results live in `var/session-18/`. The full complaint acceptance captures are in `var/frontend-validation/quality/`; the guided Samer journey captures are in `var/ux-repair/`.

The built-in browser control was unavailable, so actual rendered UI testing used Playwright Chromium. No API replies were fabricated. The delayed-response test delays a real request and then allows it through unchanged. Automated axe results are sampled evidence, not an accessibility certification. See the final machine-readable receipt for exact completed checks and any remaining test limitations.

### Verified results at the final repair snapshot

- Frontend: **63 tests passed**; production build passed.
- Affected backend checks: **18 passed** covering scheduler backoff/coverage, bank freshness, clock wakeups and approval history; one pre-existing Starlette TestClient deprecation warning.
- Focused actual-UI regression: **20 assertions passed**, including role/scope/reload notification deduplication, mobile case layout, compound identity alignment, landing favicon/tour, delayed real-response loading, tour footer visibility and idle observation.
- Idle case audit over 130 seconds: **119 → 119 events; 55 → 55 bank-feed events**.
- Guided Samer journey: **35 assertions passed**, all 12 tour highlights, real receipt/chat/call-log PNGs, actual OCR/worker, reviewer restriction, approval, both acknowledgements and ownership; case `CASE-3e84c69f80717d52`.
- A separate new complaint completed actual clarification/reply, unrelated-debit exclusion, review, both acknowledgements and persisted follow-up; case `CASE-79f16b3fd0ae1ac8`.
- Original packet download: **4 checks passed**, including exact delivered revision/digest, sourced trail paths and printable PDF output.
- Five sampled axe scans across the focused regression and guided journey reported **zero violations**. Automated scans do not establish complete accessibility.

The initial two-complaint acceptance run completed its first complaint but timed out downloading the next receipt under local load. The first guided retry also hit a 30-second selector timeout; the rerun with an appropriate bounded wait completed all 35 assertions. These timings are retained as local performance concerns, not hidden as passing results. No synthetic API response was introduced. A separate repeated-flow retry is recorded in the validation receipt if it completes.

`SESSION_2026_10_18_VALIDATION.json` is the checked-in receipt. Large screenshots and generated documents remain under ignored `var/` paths.

The optional additional repeated-flow retry was stopped after making no progress beyond entrance/readiness. It is **not counted as passing**. Local responsiveness with accumulated practice data remains a blocker to calling this production-ready; the separately completed guided and clarification journeys remain valid evidence.
