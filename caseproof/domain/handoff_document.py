"""Readable, script-free rendering of an immutable delivered packet."""

import json
from html import escape

from caseproof.domain.brief import readable_brief


def render_document(packet):
    def e(value):
        return escape(str(value), quote=True)

    report = packet.get("report_update", {})
    rows = []
    for position in report.get("traced_amounts", []):
        rows.append(
            "<tr>"
            + "".join(
                "<td>" + e(value) + "</td>"
                for value in (
                    position.get("account", "Unknown"),
                    f"INR {position['amount_minor'] / 100:,.2f}",
                    position.get("status", "Unknown"),
                    " → ".join(position.get("path", [])),
                    "; ".join(position.get("sources", [])),
                )
            )
            + "</tr>"
        )
    brief = packet.get("investigation_brief")
    prose = readable_brief(brief) if brief else packet.get("summary", "")
    return (
        """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy"
content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>CaseProof handoff document</title><style>
body{font:15px/1.55 Arial,sans-serif;color:#15161a;margin:40px auto;max-width:1080px;padding:0 24px}
h1{font-size:32px}h2{border-top:1px solid #ddd;padding-top:24px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}
table{border-collapse:collapse;width:100%;font-size:12px;table-layout:fixed}
th,td{border-bottom:1px solid #ddd;padding:10px;text-align:left;
vertical-align:top;overflow-wrap:anywhere}
.notice{background:#f5f4f0;border-left:4px solid #2b46d4;padding:18px}
.identity{font:12px/1.6 monospace;overflow-wrap:anywhere}
@page{size:A4;margin:16mm}@media print{body{margin:0;padding:0;font-size:10pt}
thead{display:table-header-group}tr{break-inside:avoid}h2{break-after:avoid}}
</style></head><body><header><p>CaseProof · Synthetic bank practice</p>
<h1>Investigation handoff</h1>
<p class="identity">"""
        + e(packet["packet_id"])
        + " · revision "
        + e(packet["revision"])
        + " · digest "
        + e(packet.get("audit", {}).get("digest", ""))
        + """</p></header>
<p class="notice">Exact approved and delivered content.
Bank observations are not confirmed holds or recovery.
This document does not establish a freeze, refund, regulatory filing or closed investigation.
Use your browser's Print / Save as PDF to retain this readable copy.</p>
<h2>Cited investigation brief and decision</h2><pre>"""
        + e(prose)
        + """</pre>
<h2>Money trail — sourced positions</h2><p>Positions and paths from the approved computation.
A recoverable position means potentially available at its observation,
subject to freshness and bank confirmation.</p>
<table><thead><tr><th>Account</th><th>Attributed amount</th><th>Observation state</th>
<th>Transfer path</th><th>Sources</th></tr></thead><tbody>"""
        + (
            "".join(rows)
            or '<tr><td colspan="5">No sourced positions established for this packet.</td></tr>'
        )
        + """</tbody></table>
<details><summary>Bank observations and transfer records</summary><pre>"""
        + e(json.dumps(report.get("balance_observations", []), indent=2, ensure_ascii=False))
        + """</pre></details>
<h2>Approved packet appendix</h2><p>The complete source-linked packet is available below,
including unresolved matters, request history, approval rationale and provider provenance.
Delivery receipts and current follow-up remain in the workspace;
they may occur after this packet was approved.</p>
<details><summary>Inspect complete original packet</summary><pre>"""
        + e(json.dumps(packet, indent=2, ensure_ascii=False))
        + "</pre></details></body></html>"
    )
