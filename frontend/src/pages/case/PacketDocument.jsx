import React, { useState } from "react";
import { Printer } from "lucide-react";
import { formatMinor, time, label } from "../../models/caseView.js";
import { GeminiStatement } from "../../components/Gemini.jsx";

// The system's end product, rendered as the document the two receivers got:
// the bank case ticket (full approved brief) and the cybercrime report update.
export default function PacketDocument({ packet }) {
  const [raw, setRaw] = useState(false);
  const brief = packet.investigation_brief || {};
  const approval = brief.approval || packet.audit?.approval || {};
  const update = packet.report_update || {};
  const clock = update.clock || packet.audit?.clock_at_approval || {};
  return (
    <article className="packet-doc" aria-label="Delivered report">
      <header className="packet-head">
        <div>
          <div className="eyebrow">Synthetic report · as delivered</div>
          <h2>Payment scam investigation report</h2>
          <p className="muted mono">
            {packet.packet_id} · case {brief.case_id} · approved revision{" "}
            {packet.revision}
          </p>
        </div>
        <div className="row gap8 packet-actions">
          <button className="btn sm" onClick={() => window.print()}>
            <Printer size={13} /> Print / save as PDF
          </button>
          <button className="btn sm ghost" onClick={() => setRaw((x) => !x)}>
            {raw ? "Hide" : "Show"} raw data
          </button>
        </div>
      </header>

      <section className="packet-decision">
        <div>
          <small>Reviewer decision</small>
          <b>{label(approval.disposition || "")}</b>
        </div>
        <div>
          <small>Approved</small>
          <b>{approval.at ? time(approval.at) : "—"}</b>
        </div>
        <div>
          <small>Confirmed disputed</small>
          <b>{formatMinor(brief.totals?.confirmed_disputed_minor || 0)}</b>
        </div>
        <div>
          <small>Golden hour at approval</small>
          <b>
            {clock.golden_hour_remaining > 0
              ? `${Math.round(clock.golden_hour_remaining)} min left`
              : "Elapsed"}
          </b>
        </div>
      </section>
      {approval.reason && (
        <p className="packet-reason">
          <b>Reviewer rationale:</b> {approval.reason}
        </p>
      )}

      <h3>1 · Bank case ticket</h3>
      <p>{brief.summary || packet.summary}</p>
      <table className="packet-table">
        <caption>Payments</caption>
        <thead>
          <tr>
            <th>Time</th>
            <th>Payee</th>
            <th>Status</th>
            <th>Source</th>
            <th className="num">Amount</th>
          </tr>
        </thead>
        <tbody>
          {(brief.payments || []).map((p) => (
            <tr key={p.txn_id}>
              <td>{time(p.at)}</td>
              <td className="mono">{p.payee || p.txn_id}</td>
              <td>{label(p.status)}</td>
              <td>{label(p.source_category)}</td>
              <td className="num">{formatMinor(p.amount_minor)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <table className="packet-table">
        <caption>Chronology</caption>
        <tbody>
          {(brief.chronology || []).map((e, i) => (
            <tr key={i}>
              <td>{time(e.at)}</td>
              <td>{e.event}</td>
              <td className="muted">{label(e.source_category)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {(brief.unknowns?.length > 0 || packet.unresolved?.length > 0) && (
        <div className="packet-gaps">
          <b>Stated gaps</b>
          <ul>
            {(brief.unknowns || []).map((u, i) => (
              <li key={"u" + i}>
                {typeof u === "string" ? u : u.label || u.fact || label(u.kind)}
              </li>
            ))}
            {(packet.unresolved || []).map((g) => (
              <li key={g.gap_id}>
                {label(g.required_fact)} · resolvable by {g.resolvable_by}
              </li>
            ))}
          </ul>
        </div>
      )}

      <h3>2 · Cybercrime report update (for receiving banks)</h3>
      <GeminiStatement caseId={brief.case_id} revision={packet.revision} />
      <table className="packet-table">
        <caption>Disputed debits</caption>
        <thead>
          <tr>
            <th>Time</th>
            <th>Beneficiary</th>
            <th>Reference</th>
            <th className="num">Amount</th>
          </tr>
        </thead>
        <tbody>
          {(update.debits || []).map((d) => (
            <tr key={d.txn_id}>
              <td>{time(d.ts)}</td>
              <td className="mono">{d.beneficiary}</td>
              <td className="mono">{d.reference}</td>
              <td className="num">{formatMinor(d.amount_minor)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <table className="packet-table">
        <caption>Where the money was traced</caption>
        <thead>
          <tr>
            <th>Account</th>
            <th>Status</th>
            <th>Path</th>
            <th className="num">Amount</th>
          </tr>
        </thead>
        <tbody>
          {(update.traced_amounts || []).map((t, i) => (
            <tr key={i}>
              <td className="mono">{t.account}</td>
              <td>{label(t.status)}</td>
              <td className="mono muted">{(t.path || []).join(" → ")}</td>
              <td className="num">{formatMinor(t.amount_minor)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <table className="packet-table">
        <caption>Balances reported by receiving banks</caption>
        <tbody>
          {(update.balance_observations || []).map((b) => (
            <tr key={b.update_id}>
              <td>{b.reporting_bank}</td>
              <td className="mono">{b.account}</td>
              <td>{time(b.reported_at)}</td>
              <td className="num">{formatMinor(b.balance_minor)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">
        Left the banking system: {formatMinor(update.left_system_minor || 0)} ·
        Unaccounted: {formatMinor(update.unaccounted_amount_minor || 0)}.
        Balances are observations at the reported time, not confirmed holds or
        recoveries.
      </p>
      <footer className="packet-foot muted">
        {brief.limitations} Snapshot digest{" "}
        <span className="mono">{brief.digest?.slice(0, 16)}</span>.
      </footer>
      {raw && (
        <pre className="safe-json">{JSON.stringify(packet, null, 2)}</pre>
      )}
    </article>
  );
}
