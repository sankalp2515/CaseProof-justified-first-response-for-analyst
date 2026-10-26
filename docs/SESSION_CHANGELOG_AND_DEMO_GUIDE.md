> **18 October provider correction:** The deployed staging workflow already passed a live Google Document AI + Vertex AI Gemini journey on 17 October (see INTEGRATION_RESULTS.md). Earlier wording below described the isolated local regression environment too broadly. It must not be read as a claim that deployed Gemini is unavailable or unverified. Google staff sign-in and institutional bank connectivity are separate capabilities. Current repairs and validation are recorded in SESSION_2026_10_18_UX_AND_ANALYST_VALUE.md.

# CaseProof: previous integration and UX repair record

Worktree: `C:/Users/sanka/.codex/worktrees/landing-demo-journey/CaseProof`

Branch: `codex/landing-demo-journey`

Baseline integration commit: `d757065`. This document records the subsequent screenshot-led repair session too. Deployment and the other checkout remain separate. No cloud configuration or Google credentials were enabled.

## Previous session

The accepted landing HTML, styles, fonts and interactive illustration were integrated at `/`. Practice actions open the reporting portal; the analyst link opens the workspace. React remains under `/app/` with hash routing. The landing was compared against the accepted preview, including its palette, typography, hero, framing and mobile navigation.

Victim-to-analyst demo navigation was added, including a submission shortcut to the exact new case. Multiple uploads and server-generated practice receipt/chat/call-log images were connected to real intake and processing. Local samples are simulator documents; the optional live AI writing path remained unverified.

Golden-hour timing was made available before OCR from the customer's selected bank payments. The selectable practice catalogue was improved so every primary customer had a scam-payment scenario. Old bank history was preserved rather than re-timestamped. Local timestamp extraction was corrected to preserve explicit offsets.

The existing immutable delivered packet was given a readable HTML download containing the cited brief, approval identity, revision/digest, sourced trail positions, bank observations and original packet appendix. A real UI download and three-page printed PDF were checked.

Validation at that point included 360 Linux backend tests, 49 frontend tests, two real complaint journeys, mixed-evidence processing, both simulator acknowledgements and sampled accessibility scans. **Those checks missed the tour's actual interactive intake and short-height placement defects.** The earlier twelve-click tour check established navigation, not a successful guided submission. This session replaces that weak check with a tour-driven reporting and handoff journey.

## What the screenshots and reproduction established

| Report | Finding | Repair |
|---|---|---|
| Search input alignment | The global stacked-form selector added a second border and `6px 0 16px` margins inside the search container. The input measured 41.5px high inside a 34px shell. | A specific compound-control rule resets margins, padding, border and sizing while preserving the enclosing search style. Checked at 1242, 627 and 390px widths. |
| Demo identity alignment | A header control inherited form layout while sharing space with unrelated header actions. | Explicit caption/select geometry, consistent left edges, fixed control sizing and responsive header spacing. |
| Tour footer hidden | Placement assumed a 300px card. At a 668px viewport, the reproduced footer extended below the viewport and the card bottom reached about 730px. | Measure actual card height, clamp placement to the viewport, scroll the body independently, retain visible actions and provide Minimise/Show guidance. Checked down to 400px viewport height. |
| Step 2/3 blocked or skipped | Several required customer/payment actions had been combined but Next still skipped directly to a narrative explanation. Back/resume could also incorrectly keep Next disabled. | Intake highlights follow the actual page, wait for the action and advance on real form state. Revisiting an already satisfied action permits Next. Minimisation exposes all page controls. |
| Tour opened `/entry` | The introduction retained an obsolete route to the separate entry screen. | Introduction stays at the user's current landing destination. The legacy entry URL remains compatible but is not a prerequisite for the tour. |
| Tour could finish without a handoff | Navigating through explanations was not proof of delivery. | The last highlight queries the actual workflow. Finish requires the current revision's completed delivery and an explicitly saved follow-up owner/next action (`version > 0`). Historical receipts or default owner text do not qualify. |
| Queue and Cases looked identical | Both routes rendered essentially the same dashboard. | Queue retains priority triage and current-session controls. Cases now opens a distinct all-accessible case register, newest reports first, with status, owner and delivery-history columns and filters. Server authorization still controls access. |
| Payment list order | Payments were rendered in backend return order. | Sort copies of the bank rows by timestamp descending, with stable ties. Bank records are not modified. |
| First-contact confusion | The form did not explain the difference between contact and payment time. | Clearer label and help text. A contact time after a selected payment requires correction, omission if unknown, or explicit confirmation that it is the account being reported. The bank debit clock is never changed to make the story fit. |
| Disabled AI checkbox | Local mode cannot generate through an unconfigured live model. The disabled control suggested a broken feature. | Local mode shows a plain explanation and working simulator-sample actions. AI writing is offered only when the server reports a configured live provider. No simulated Gemini success. |
| “Local OCR and literal rules are not Gemini.” | This was an awkward engineering disclosure rather than useful guidance. | The assessment lists its actual processing providers and explains source linkage. No unsupported Google attribution. |
| Golden-hour notification | Existing banner/bell notifications did not match the supplied prominent alert. | Added a reference-derived alert card with actual case ID, source-labelled amount, account, narrative when assessed, live bank-timed response window, Later and Open case. It deliberately says response window rather than promising a freeze. |
| Long word-chain payees | The previous OCR-oriented encoding was technically independent but unrealistic and cumbersome. | Compact bank-style practice handles, e.g. `narmada.traders.<letter suffix>@cedardemo`, and human-readable account labels in new worlds. The independent 40-bit identity is retained; financial IDs and references remain exact. Redundant synthetic suffixes were removed from visible customer names while product/evidence sandbox labels remain. |

The new catalogue uses version 5. Earlier default catalogues and session worlds remain resolvable. **Start a fresh practice session** to see the new identifiers and current timings; rewriting an old receipt or bank record would break its audit history. An older catalogue shows a refresh explanation.

The new handle suffix also exposed a real local-extractor compatibility defect: only `@fictional.invalid` had been recognised. The local allowlist now recognises the complete `@cedardemo` identifier too, with negative suffix tests so `.other` or extra characters cannot be silently truncated into a bank match. Matching and readiness requirements were not relaxed.

Background preparation previously held the shared bank writer connection across all twelve networks. It now releases the connection after each network, allowing customer reads and evidence generation to proceed between networks. A catalogue is still published ready only after all its networks are complete.

## Queue versus Cases

**Queue:** What should the response analyst inspect next? Uses backend priority order, response windows, assessment state, next action and current-practice scope. Its counters describe work in the chosen scope.

**Cases:** Where can staff find a report already recorded? Includes accessible earlier practice sessions and delivered handoffs, ordered by report time, with search, ownership, status and delivery history. An empty current queue can therefore coexist with a populated case register. “All accessible” never grants cross-tenant access.

**Deliveries:** Opens the delivery-oriented list and the case's delivery/follow-up workspace. Receipt acknowledgement is separate from a freeze, refund, filing or closed investigation.

## Analyst, reviewer and judge instructions

| Role | Responsibility | When to use it |
|---|---|---|
| Victim/customer | Identify disputed payments, describe the incident, supply evidence, answer clarification and confirm/deny a candidate debit. | Reporting and responding to a scoped request. |
| Analyst | Inspect cited facts and bank matches, review the trail, request missing information, prepare the justified first action and manage follow-up. | Investigation, clarification, preparation and follow-up. An analyst cannot approve the handoff. |
| Reviewer | Independently inspect and approve/reject the supported current revision and digest, with a reason. Urgent referral and complete handoff have separate eligibility. | At the review gate, after the relevant requirements are met. New evidence can require a new review. |

The header visibly says **Analyst investigates · Reviewer approves** and expands to explain the boundary. The tour repeats it at the cited brief and review stage. **Demo identity** is a practice role switch, not a real bank login or proof of separate human staffing. Cloud roles remain assigned by the backend from authenticated principals.

## Your timing example

A debit at **21:53 IST** and first contact entered as **22:28 IST** describe contact 35 minutes after the payment. That may be a mistake or the customer's actual account; the system should flag it rather than invent a corrected time. The new form does so. For illustration, at 22:48 the 21:53 payment would be about 55 minutes old, leaving about five minutes of its first-hour response window. Using the contact time instead would be wrong.

First contact is optional. It is not the submission time. The backend records submission time and derives priority from bank payment timestamps. A later contact entry does not restart the golden hour.

## Repeatable local journey

1. Open `http://caseproof-journey.localhost:8188/`, then Explore a practice case. Start Tour if guidance is wanted. The introduction does not detour through `/entry`.
2. Start a fresh practice session. Select Samer or any supported customer and continue to the account home. Minimise guidance while operating controls if needed.
3. Report a payment scam. Payments are newest first. Select the actual payment belonging to the story, using the displayed amount/time; do not copy a fixed amount from another session.
4. Describe what happened and how the payment was authorised. Leave unknown contact time blank. If entering a time after the payment, review the warning before explicitly retaining it.
5. Upload supported evidence or use the local sample buttons. These create labelled PNGs, not bank records. Sample-writing availability follows the connected backend capabilities; inspect the provider information for this environment. Review and submit.
6. An open analyst queue receives the alert automatically. Switching through Continue as analyst demo opens the exact submitted case. Inspect the cited brief, processing state, originals, bank matches and money trail.
7. If the backend proposes a relevant question, review/send it, answer through its scoped customer link and wait for the resulting revision. Confirm or deny any additional candidate debit explicitly. Do not invent a reply just to remove a gap.
8. As analyst, inspect the proposed handoff. Switch the labelled practice identity to reviewer only for the independent approval step. Approve only the current supported revision/digest with a reason.
9. Send the approved packet and wait for both simulator acknowledgements. Save the follow-up owner, next action and reason. Keep awaiting-external follow-up open.
10. Inspect/download the historical handoff document. Its money-trail table contains sourced positions and paths; the interactive graph remains in the workspace. The tour's final checklist requires actual current delivery and saved ownership before Finish.
11. Use Cases to find earlier records or reload to verify persistence. Start another fresh session for a newly timed world.

Not every arbitrary input can produce a complete handoff or a known money trail. Missing or conflicting source data must remain visible. Supported inputs are PNG/JPEG/UTF-8 text, 5 MiB each, with the existing six-artifact/20 MiB case cap. PDF/audio/video intake, live bank actions, live Google acceptance and a fully tagged accessible PDF remain outside the verified local scope.

## Verification evidence

The full Linux snapshot passed **361 tests** (two warnings). After the final identifier-boundary, account-label and catalogue-version refinements, **13 affected backend checks** passed, including the cloud workflow with local service doubles. Frontend tests passed **58/58**, and the production build passed. The guided journey passed **35 assertions**, two further complaint journeys passed **30 assertions**, and **13 sampled axe scans** reported zero violations. See the receipt for exact snapshot scope; these are not live Google results.

The current machine-readable receipt is `docs/UX_REPAIR_VALIDATION.json`. Local captures, actual guided-case results, repeated acceptance results, regression logs and before measurements are under `var/ux-repair/`. These include the supplied viewport sizes, narrow screens, short-height tour checks, actual OCR and simulator delivery. The built-in browser was unavailable in this session, so actual UI testing used local Playwright Chromium. Automated accessibility scans are sampled checks, not a certification.

The implementation stays in the isolated worktree. No merge, push, deployment, DNS, infrastructure, queue enablement or launch flag was performed.
