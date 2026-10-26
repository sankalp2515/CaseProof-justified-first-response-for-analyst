# Landing and demo journey integration review

Worktree: `C:/Users/sanka/.codex/worktrees/landing-demo-journey/CaseProof`
Branch: `codex/landing-demo-journey`
Starting snapshot: `3d6c5ea750c084c1cc98236fa4d6bcce4aab5c9d`
Source checkout captured: `E:/Codex Projects/CaseProof`, including its then-current uncommitted files.
Reviewed and implemented: 17 October 2026.

This work is local and separate from the deployment checkout. No deployment services, Google credentials, cloud images, infrastructure, queues or deployment flags were changed. The original ignored landing preview remains separate; its accepted HTML design is now bundled under `frontend/public/landing/`.

## Findings against the six requests

| Request | Finding | Implemented result |
|---|---|---|
| Victim-to-analyst navigation | Missing in the existing victim header and submission confirmation. | Explicit **Analyst demo** link and **Continue as analyst demo** button. Confirmation opens the exact new case and sets the labelled practice persona to analyst. These shortcuts are hidden for real cloud staff authentication; the browser cannot assign cloud roles. |
| Tour length | The existing runtime tour had 46 steps, including ordinary navigation and repeated explanations. | 12 highlights cover intake, evidence, registration, the cited brief, source originals, the observed trail, clarification, revision-bound review, delivery and audit. Chapter jumps, back/next, Escape, case tracking and restart remain. No fixed clock time is inserted into the example narrative. |
| Multiple inputs and generated evidence | Multiple files and receipt/messages/call-log kinds already existed. Discovery and truthful provider labels needed work. | Added server-owned receipt/chat/call-log PNG samples, explicit synthetic watermarks, correct evidence kinds and an optional provider-gated AI writing path. Own PNG/JPEG/UTF-8 files still pass through the real intake, OCR and worker. Upload metadata and actual processing state now appear in the victim receipt, fixing an empty received-evidence panel and improving interrupted-upload reconciliation. |
| Golden-hour testing | Clock logic already existed. Practice pools could age, and the initial queue could miss priority when a visitor first switched into staff view. | Server records provisional timing from owned bank selections before OCR/AI, without granting readiness or confirmed loss. Initial staff entry surfaces current server priority. Old windows say elapsed. Fresh pooled worlds must be current-version and younger than 15 minutes; old records are never re-timestamped. |
| Synthetic bank design | Every second selectable customer had only a small merchant payment. Random hexadecimal VPAs also introduced avoidable OCR ambiguity. | Each of 12 selectable customers gets a separate primary scam network. New human-facing VPAs encode the same independently generated 40-bit identity as readable word tokens; internal IDs and references remain exact. Version 3 catalogues preserve legacy records and existing sessions. Bank records and downstream observations exist independently of what the victim writes. |
| Actual output and document testing | The brief and immutable JSON handoff already existed, including sourced trail positions and bank observations. There was no readable document download. | Added authenticated, script-free HTML rendering of the exact delivered packet. It includes the cited brief, decision, revision/digest, sourced money-trail positions and paths, observations and a complete packet appendix. The staff UI downloads it; browser Print / Save as PDF was tested. The table contains trail data, not an invented graph or a claim of recovery. |

## Why new complaints can have a money trail

A new practice session generates and publishes a fictional bank world before the complaint. Each customer has an independently recorded primary transfer, an additional candidate debit, ordinary payments and downstream reports. Seed-dependent topology includes layering, cash-out and, for some seeds, another hop. Complaint text and AI output cannot create those bank records.

Selecting a payment establishes the customer's dispute scope. Reconciliation and bank observations determine what can be traced. An arbitrary unrelated receipt does not receive a fabricated matching network. It can remain unmatched, conflicted or incomplete, with an appropriate clarification or escalation path.

Repeated complaints about the same existing payment retain the same bank history and can be flagged as overlapping. A genuinely fresh timed scenario requires a fresh practice session. This preserves causality and immutability.

Golden-hour priority is deterministic response timing. It is not a model confidence score, a finding of fraud, a promise of a freeze or a recovery estimate. Before assessment, selected-bank timing is provisional and confirmed loss remains zero.

## Evidence-generation and OCR boundaries

Local validation used real Tesseract, local literal extraction rules, a durable worker and both simulator receivers. Local samples are labelled **bank-simulator**, never Gemini.

The optional AI path calls the existing configured live Gemini/Vertex provider, uses its cache and call caps, validates a bounded response and rejects invented numeric, payment or credential fields. The server adds monetary anchors from the selected owned bank record. Missing live configuration disables the AI option; provider failure is explicit. This path is implemented but has not been exercised against live Google here.

The local stress test found two separate issues:
- UTC timestamps in sample receipts were being interpreted as IST. Explicit offsets now survive literal extraction, and sample receipts show an explicit local date and IST time.
- Fonts alone do not eliminate zero/O ambiguity in arbitrary identifiers. New demo VPAs use readable word encodings; simulator receipts follow the existing explicitly labelled cropped-reference pattern. Matching still requires sourced payee and time against bank records. Actual ambiguous full receipts remain subject to verification. Matching, financial validation and readiness were not relaxed.

The bundled JetBrains Mono face is derived from the existing Studio font dependency; its OFL notice is included under `caseproof/assets/fonts/`.

## Reusable click-through for a new supported complaint

1. Open the isolated landing preview at `http://caseproof-journey.localhost:8188/`. The custom localhost name keeps this browser's practice cookies apart from other local project tabs.
2. Choose **Explore a practice case**. Choose **Start a fresh practice session** and wait for the new customer catalogue.
3. Select any customer, including Samer, then continue. Choose **Report a payment scam**.
4. Select the recent safe-account payment for a golden-hour scenario. Leave the separate refund-like debit unselected unless it is genuinely part of the intended fictional complaint. Old and ordinary payments remain valid report choices, but need not produce the same priority or trail.
5. Describe what happened in your own words and choose the payment-authorisation account. The tour offers an editable fictional example.
6. Upload supported evidence, or create a labelled synthetic receipt/chat/call log. Choose the correct evidence kind for your own files. Inspect the receipt-crop notice. Local mode keeps the AI checkbox unavailable.
7. Review and submit. Receiving evidence is separate from assessment. Use **Continue as analyst demo** to open this exact case; the header shortcut also opens the queue.
8. Wait for actual processing. Inspect the brief, original evidence, bank matches, trail and unresolved matters. Priority is based on server timing, not a fixed demo countdown.
9. If the request engine proposes a meaningful question, review and send it. Open its issued scoped reply, provide relevant evidence or notes, then complete the reply. Wait for the resulting revision.
10. In the victim report, explicitly confirm or deny an additional candidate payment. It is never automatically included in confirmed disputed loss.
11. An analyst cannot approve. Switch the labelled demo persona to reviewer, inspect current readiness and the draft, enter a reason and approve the current revision/digest only when eligible. Resolve genuine gaps; a complete handoff is not guaranteed for arbitrary inputs. Urgent referral has separate eligibility.
12. Send approved content. Wait for **both** simulator acknowledgements. Assign owner, next action and reason; confirm awaiting-external follow-up and persistence after reload.
13. In delivered packet history, inspect the original packet or choose **Download handoff document**. Open the HTML and use Print / Save as PDF. It remains the approved historical revision even after reassessment.
14. Start another fresh practice session for a new timed bank world, or another complaint in the current session when testing persistence and overlapping reports.

The 12-highlight tour explains consequential decisions. It does not silently perform approval, fabricate a missing answer or imply that merely reaching the final highlight completed delivery.

## Validation and artifacts

The portable receipt is `docs/LANDING_DEMO_VALIDATION.json`. Frontend tests passed 49/49; the production build passed. Browser checks passed 30 end-to-end assertions across two fresh complaints, 19 mixed-evidence/document assertions and 16 built-nginx visual/routing/keyboard assertions. Fifteen sampled axe scans reported zero violations. Three local cloud-adapter contract tests also passed; they are not live Google verification.

Actual machine-readable results and screenshots are kept in ignored local validation folders:
- `var/frontend-validation/quality/acceptance.json`: two fresh complaint journeys, 30 assertions, 10 sampled axe scans.
- `var/journey-validation/enhancements.json`: mixed receipt/chat/call-log/own-file Samer journey, tour, priority, actual OCR, document identity and PDF checks.
- `var/journey-validation/built-visual.json`: nginx build, responsive overflow, keyboard, routing and configuration checks.
- `var/journey-validation/frontend-tests.log` and `build.log`.
- `var/journey-validation/handoff.html`, `handoff.pdf`, rendered screenshots and before/after landing captures.

The earlier full isolated Linux regression passed 358 tests. A final source-snapshot regression and current browser repetition are recorded in the final validation receipt alongside this report. Subsequent focused API checks passed 26 tests, including the cloud-adapter contract with explicit service doubles; those doubles do not establish live Google behaviour.

The cloud adapter review also identified an existing naming defect: serialization separated the dataset and manifest customer lists. Their names are now synchronized, with all 12 catalogue entries asserted in the cloud contract journey. This was verified with adapter doubles, not live Google.

The native Windows run exposed missing/platform-specific OCR and atomic-replace differences plus CRLF alteration of the frozen corpus checksum. Frozen bytes were restored from Git in this worktree only. `.gitattributes` now protects hashed corpus fixtures from newline conversion. The production-like Linux test environment is the regression target.

Final Linux source-snapshot regression: **360 passed, 2 warnings, 521.01 seconds**. The snapshot preceded the final cloud catalogue-name synchronization; the three affected cloud contract tests passed again after that fix. Warnings were the Starlette test-client deprecation and an intentional oversized-image safety fixture.

## Visual comparison ledger

| Point | Reference and rendered evidence | Result |
|---|---|---|
| Palette | Original landing `styles.css` / `refined.css`, current built captures | Existing background #f5f4f0, ink #15161a, primary #2b46d4, evidence green and advisory purple retained. |
| Typography | Original local Inter/Source Serif/mono assets, built 1265/1440 captures | Same font assets, hero scale, serif trail heading and control typography retained. |
| First viewport | Original `landing-preview/refined-desktop.png`, `built-landing-1265.png` | Same hero copy, ordering, centred hierarchy and framed illustrative workspace. Added necessary staff navigation. |
| Component framing | Existing landing markup and current captures | Same stage tabs, node/inspector anatomy, borders, radii and media framing. The illustration remains explicitly labelled. |
| Calls to action | Original preview anchors versus built routing checks | All practice CTAs now open actual reporting. Illustration links still inspect the labelled example. Mobile navigation exposes staff access. |
| Victim sample controls | Current mobile and desktop evidence captures | Replaced an inappropriate green monospace financial-bound style with the existing blue-soft panel, Inter body text and full-width mobile actions. |
| Responsive and keyboard | 390/768/1265/1280/1440 captures and test records | No observed body overflow at sampled widths. Skip link, illustration arrow keys, tour heading focus and Escape verified. |

Above-the-fold hero and value-proposition copy is preserved. Intentional copy changes connect real practice actions, add staff navigation, remove standalone-preview wording and explain the receipt crop and actual sample-provider mode.

## Remaining limits and launch blockers

**Backend/product:** Real bank and institutional integrations remain outside this synthetic prototype. A trail depends on available bank records; an arbitrary external document cannot produce an invented downstream path. The existing case cap is six artifacts / 20 MiB. Filling every slot initially can leave no capacity for later clarification uploads or notes; leave room during evaluation. That quota/reply policy needs a separate product decision before a production claim.

**Frontend/evidence:** Intake supports PNG, JPEG and UTF-8 text, up to 5 MiB per file. PDF, audio recordings and video are not supported inputs. A call-log screenshot or text note is supported; call audio is not. The readable handoff includes a source table and appendix; the interactive graph itself stays in the workspace. The PDF is a tested print rendering, not a new server-side PDF API.

**Cloud/auth:** Live Google sign-in, live Gemini/Document AI generation and extraction quality, cloud performance, quota and delivery acceptance remain for the deployment/staging owner. These local checks do not verify them. No cloud launch gate or infrastructure flag was set.

**Accessibility/launch:** Sampled automated scans are not a full accessibility certification. The printed PDF is not tagged. Real-user evaluation, broader assistive-technology testing, unfamiliar-input quality and operational/security launch review remain necessary.

## Frontend service and deployment boundary

The captured source already defines a separate `frontend` service in `compose.yaml`, backed by `frontend/Dockerfile`. Its nginx service serves the landing at `/` and React at `/app/`, with same-origin API routing. The isolated preview uses its own nginx container on 8188 and API on 8184. Serving static files through a gateway is also a normal architecture; a service name alone does not prove production readiness. No deployment service was rebuilt or switched by this task.

## Merge handoff

Only this worktree contains these implementation changes. The base snapshot captured the source checkout's uncommitted deployment work without changing its files or index. The implementation is saved as a subsequent commit for review. Integrate that implementation commit after the deployment owner finishes their work; do not reset the deployment checkout or blindly replace its backend files. Review overlapping API/cloud changes normally. No merge or push was performed here.
