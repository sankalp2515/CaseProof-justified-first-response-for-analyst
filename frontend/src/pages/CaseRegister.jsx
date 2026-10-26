import React, { useState } from "react";
import { Search, ArrowRight } from "lucide-react";
import {
  Card,
  CardH,
  Status,
  ErrorBanner,
  Loading,
  Empty,
} from "../components/live.jsx";
import { time, formatMinor, label } from "../models/caseView.js";
import { go } from "../router.js";
export default function CaseRegister({ resource }) {
  const [query, setQuery] = useState(""),
    [state, setState] = useState("all");
  const all = resource.data?.cases || [];
  const rows = [...all]
    .filter(
      (c) =>
        (state === "all" ||
          (state === "followup"
            ? c.followup?.state === "awaiting_external"
            : c.status === state)) &&
        [c.case_id, c.customer_account, c.status, c.followup?.owner]
          .join(" ")
          .toLowerCase()
          .includes(query.toLowerCase()),
    )
    .sort(
      (a, b) =>
        Date.parse(b.reported_at) - Date.parse(a.reported_at) ||
        a.case_id.localeCompare(b.case_id),
    );
  return (
    <div className="page case-register">
      <div className="page-h">
        <div>
          <h1>Case register</h1>
          <p>
            Search all cases you can access, including earlier practice sessions
            and delivered handoffs. Newest reports first.
          </p>
        </div>
        <button className="btn" onClick={resource.reload}>
          Refresh register
        </button>
      </div>
      <ErrorBanner error={resource.error} onRetry={resource.reload} />
      <Card>
        <CardH
          title={`All accessible cases · ${all.length}`}
          sub="History and ownership; use Queue for response-priority triage."
        >
          <label className="search">
            <Search size={14} />
            <input
              aria-label="Search case register"
              placeholder="Case, account, owner or state…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
        </CardH>
        <div className="queue-filters">
          {[
            ["all", "All records"],
            ["processing", "Processing"],
            ["awaiting_information", "Awaiting information"],
            ["ready_for_review", "Review ready"],
            ["followup", "Awaiting external"],
            ["completed", "Delivered"],
          ].map(([id, name]) => (
            <button
              className={"btn sm " + (state === id ? "dark" : "ghost")}
              key={id}
              onClick={() => setState(id)}
            >
              {name}
            </button>
          ))}
        </div>
        {resource.loading ? (
          <Loading />
        ) : (
          <div className="table-scroll">
            <table className="t">
              <thead>
                <tr>
                  <th>Case / account</th>
                  <th>Reported</th>
                  <th>Confirmed disputed</th>
                  <th>State / owner</th>
                  <th>Delivery history</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.case_id}>
                    <td>
                      <button
                        className="case-link"
                        onClick={() => go(`/staff/cases/${c.case_id}/overview`)}
                      >
                        {c.case_id}
                        <ArrowRight size={12} />
                      </button>
                      <small className="mono muted">{c.customer_account}</small>
                    </td>
                    <td>{time(c.reported_at)}</td>
                    <td className="num">
                      {formatMinor(c.confirmed_disputed_minor)}
                    </td>
                    <td>
                      <Status value={c.status} />
                      <small>{label(c.followup?.owner || "Unassigned")}</small>
                    </td>
                    <td>
                      {c.historical_deliveries?.length
                        ? `${c.historical_deliveries.length} receiver acknowledgements`
                        : "No acknowledged delivery"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!rows.length && (
              <Empty>
                {query || state !== "all"
                  ? "No records match these filters."
                  : "No accessible case records yet. Submit a report to create one."}
              </Empty>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
