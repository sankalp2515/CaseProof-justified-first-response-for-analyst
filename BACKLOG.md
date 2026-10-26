# Backlog

Priority: P0 before release claims; P1 strengthens the demonstration; P2 institutional production work.

| Priority | Work | Status | Owner / dependency |
| --- | --- | --- | --- |
| P0 | Frontend/backend consolidation | PASS: automated and manual complete-case runs | Internal |
| P0 | Microservice local topology (separate frontend) | PASS: seven Compose services on one network; 30/30 browser checks; fault injection | Internal |
| P0 | Scanner competing-load latency | PASS: resident engine; scans ≤1.3s under 4-CPU competing load (was 63–120s) | Internal |
| P0 | Native dependency release-risk assessment | PASS (engineering triage): [assessment](docs/NATIVE_DEPENDENCY_RISK.md); unused ClamAV parsers disabled; re-scan staged digests | Internal/vendor updates |
| P0 | Real Document AI/Vertex unfamiliar-input evaluation | PENDING: staging works end to end; N28 and the manual O/0 receipt not yet run through Document AI | Internal (staging available) |
| P0 | Domain, identity, state ownership and costed staging configuration | DONE: sslip.io domain + managed TLS, practice personas, protected remote state, digest-pinned images ([record](docs/DEPLOYMENT.md)) | Project owner |
| P0 | Real Google IAM, transactions, retries and ingress acceptance | PARTIAL: ingress/IAM privacy and a full complaint-to-delivery run verified on staging; Firestore contention, forced Tasks recovery and WAF blocking not yet tested | Internal |
| P1 | Guided demo tour (victim → analyst, golden hour) | DONE: 46 steps, every analyst component explained; verified locally and on staging | Internal |
| P1 | Fixture/practice bootstrap under competing work (B11) | PASS: sequential median 1.7s (was 5.7s); pooled claim 0.14s; 5-concurrent p95 under load 18s (was 79s) | Internal |
| P1 | Larger sustained capacity benchmark | PASS (local, bounded): 60/60 complaints at 5/10/15 concurrent; 2 workers cut 15-concurrent p95 to ~57s | Internal |
| P1 | Partition worker background polling across replicas (local stack) | IMPLEMENTED: single leader lease (failover 43s), per-replica heartbeat, race-safe cursors, interactive-priority inheritance; 2-worker capacity rerun pending | Internal |
| P1 | FCA independent evaluation | READY TO START: Google staging is live | External dataset/access available |
| P1 | Human time/rework comparison and differentiation evidence | UNMEASURED: same-input field parity is not superiority | Actual participants |
| P1 | Practitioner feedback | EXCLUDED from current execution | Human |
| P1 | Final submission package | EXCLUDED from current execution | User/competition logistics |
| P2 | Real bank access, institutional policy/retention/security approval | OUTSIDE synthetic prototype scope | Institution |

Implemented: cited investigation brief; distinct urgent/full readiness;
separate source provenance; preloaded synthetic bank records; deterministic
money/trace/request rules; immutable revision-bound review; durable jobs/outbound
intents; deduplicated simulator receipts; owned post-delivery follow-up; prepared
Google adapters with no silent local fallback; separate frontend, API, worker,
OCR, feed and simulator services.

Current validation: Google staging end-to-end pass (real Document AI + Gemini, both
receivers); backend regression, 48 frontend tests, 30 local browser checks with zero
accessibility violations, fault injection and 3 mocked Terraform plans. Details:
[validation](docs/INTEGRATION_RESULTS.md). No production readiness or measured
human-time benefit is claimed.
