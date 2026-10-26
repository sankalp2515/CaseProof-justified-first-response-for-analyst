# Native dependency release-risk assessment — 17 October 2026

Scope: the prepared Trixie cloud runtime image and the ClamAV scanner image.
Source data: Grype reports `var/readiness/cloud-runtime-dependencies.json` and
`var/readiness/scanner-dependencies-final.json` (generated 17 October 2026),
plus `pip-audit` reports for the locked Python set (no known Python findings).
This is an engineering triage, not an independent security certification and
not a zero-vulnerability claim. Re-run both scanners on the exact image digests
chosen for staging; vulnerability databases change daily.

## Summary

| Group | Count (scanner image) | Assessment | Action |
| --- | --- | --- | --- |
| `/usr/bin/openssl` binary CPE matches (2 Critical, 11 High "fixed in 3.5.8") | 13 | Grype matched the CLI binary by upstream version; Debian's `openssl`/`libssl3t64` packages are not flagged in the Debian namespace, so fixes are backported. Probable backport false positives. | Accept; confirm the Debian security tracker for each CVE against the staged digest. The runtime never invokes the `openssl` CLI. |
| ClamAV 1.4.6 parser CVEs (12 High, 1 Medium, Debian state "wont-fix") | 13 | Real upstream findings in PE, PESpin, FSG, 7z, DMG, XAR, ALZ, GPT, Mach-O, PDF, InstallShield and HTML/CSS parsers. 1.4.6 is the pinned LTS engine; no fixed LTS was available at assessment time. | **Mitigated in configuration** (below). Upgrade the engine when a fixed LTS is published. |
| util-linux / glibc / gcc runtime / ncurses / perl-base / acl ("wont-fix") | ~60 | Debian-assessed minor or not-applicable to container use (setuid tools, local login, compiler paths). No reachable path from HTTP evidence input identified. | Accept; track Debian point releases and rebuild on base-image updates. |
| zlib1g CVE-2026-85091 (High, "not-fixed") | 1 | Affects the `gzwrite`/`gzprintf` non-blocking path. CaseProof never writes gzip streams; Pillow decodes PNG via inflate only. | Accept; rebuild when Debian ships a fix. |
| gzip binary CVE-2026-41992 (High, no fix state) | 1 | LZH decompression in the `gzip` CLI. Not invoked by the application. | Accept. |
| Medium/Low/Negligible | ~140 | Not individually triaged. | Track with base-image refreshes. |

The cloud runtime image shows the same OS findings minus the ClamAV group.

## ClamAV attack-surface reduction

Evidence is limited to validated PNG, JPEG and text before it reaches the scanner
(`caseproof/adapters/object_validation.py`). The resident engine configuration in
`local_services/cloud_scanner.py` disables every parser family named by the open
findings and not needed for those types: `ScanArchive`, `ScanPE` (covers PESpin,
FSG and other PE unpackers), `ScanELF`, `ScanOLE2`, `ScanPDF`, `ScanSWF`,
`ScanHTML`, `ScanXMLDOCS`, `ScanHWP3`, `ScanOneNote` and `ScanMail`. Image and
signature-body matching remain enabled; EICAR is still detected
(`var/readiness/scanner-clamd/hardened-*.log`). Unit tests assert these settings.

Residual risk: whole-file signature matching still runs on attacker-supplied
bytes; ClamAV's file-type detection still reads headers; Mach-O and GPT parsing
are not individually switchable in 1.4.6 (GPT falls under archive/partition
handling, which is disabled). A polyglot image carrying an embedded executable
will not have that executable parsed or unpacked. The scanner runs as an
unprivileged user in its own Cloud Run service with no data-store permissions,
and only the worker identity can invoke it. Scanner failure fails closed.

## Release decision

No finding blocks an authorized, synthetic-data staging deployment once the
staged digests are re-scanned and any new Critical/High result with a reachable
path is triaged. Production use would additionally require an institution's
vulnerability-management process, a fixed ClamAV LTS and independent review.
