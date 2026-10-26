# Security boundaries

This is a synthetic local prototype. Only the `frontend` service publishes a port,
on host loopback; other services are reachable only on the Compose network. No real
customer data or institutional authority is represented. The Google staging deployment is synthetic-only.

- Staff local roles are explicit demonstration personas. Prepared cloud mode uses
  verified Google ID tokens and server-mapped roles/tenants; demo headers do not
  authorize cloud staff access.
- The Google staging deployment enables practice personas
  (`CLOUD_PRACTICE_PERSONAS`): Analyst/Reviewer without sign-in, honoured only with a
  valid practice-session cookie and confined to that visitor's own synthetic tenant.
  Admin actions, the shared tenant and other visitors' cases stay unreachable. Real
  institutional use would switch this off and use Google staff identity.
- Victim sessions use scoped cookies; clarification links are bounded capabilities.
  Do not log/share link tokens. Token pages use no-referrer and no-store headers.
- Request bodies and image dimensions are bounded; supported evidence is PNG,
  JPEG and text. Missing/invalid source anchors do not become verified facts.
- Money calculations, readiness, revision/digest checks, permissions and delivery
  are deterministic. AI interpretation remains advisory.
- Google evidence enters quarantine and requires a digest-matching clean scan.
  Scanner unavailable, malformed/stale signatures and errors fail closed.
- ClamAV 1.4.6 and image digests are pinned. The scanner runs one resident engine
  with executable, document, mail and archive parsers disabled; evidence is limited
  to validated PNG/JPEG/text. Native findings are triaged in
  [native dependency risk](NATIVE_DEPENDENCY_RISK.md); raw matches include backport
  false positives and unresolved vendor findings. This is not a zero-vulnerability
  or production-security claim.
- Local data, credentials, environment secrets, Terraform state, generated browser
  reports and dependency/build directories are excluded from Git and build context.

The local `ocr` image stays on Bookworm to preserve the frozen OCR evaluation
environment; it is not a production image recommendation. Prepared cloud and
scanner images use Trixie.

Real identity, retention, institutional access, incident operations and independent
security approval are production requirements beyond a synthetic demonstration.
