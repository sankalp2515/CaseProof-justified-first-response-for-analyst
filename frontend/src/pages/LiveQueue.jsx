import React, { useState } from "react";
import {
  Search,
  ArrowRight,
  Clock,
  Activity,
  FileText,
  RefreshCw,
  Inbox,
} from "lucide-react";
import {
  Card,
  CardH,
  Badge,
  Status,
  ErrorBanner,
  Loading,
  Empty,
} from "../components/live.jsx";
import { useResource, useSession } from "../state/resources.jsx";
import { apiRequest } from "../api/client.js";
import { formatMinor, time, remaining, label } from "../models/caseView.js";
import { go } from "../router.js";
import CaseRegister from "./CaseRegister.jsx";
export default function Queue({ mode, activeResource, scope, setScope }) {
  const { persona } = useSession(),
    [q, setQ] = useState(""),
    [filter, setFilter] = useState("all");
  const resource = activeResource;
  if (mode === "cases") return <CaseRegister resource={resource} />;
  const all = resource.data?.cases || [],
    counts = resource.data?.counts;
  const rows = all.filter(
    (c) =>
      (mode !== "deliveries" ||
        c.historical_deliveries?.length ||
        c.deliveries?.length) &&
      (filter === "all" || c.status === filter) &&
      [c.case_id, c.customer_account, c.victim_summary, c.status]
        .join(" ")
        .toLowerCase()
        .includes(q.toLowerCase()),
  );
  const open = (c) => go(`/staff/cases/${c.case_id}/overview`),
    next = all[0];
  return (
    <div className="page command-center">
      <div className="page-h">
        <div>
          <h1>
            {mode === "deliveries"
              ? "Report deliveries"
              : mode === "cases"
                ? "Case register"
                : "Command Center"}
          </h1>
          <p>Cedar Demo Bank · Fraud Operations · payment-scam response</p>
        </div>
        <div className="right row gap8">
          <button className="btn" onClick={() => resource.reload()}>
            <RefreshCw size={13} />
            Refresh
          </button>
          <button className="btn primary" onClick={() => go("/victim/start")}>
            Open reporting portal
            <ArrowRight size={14} />
          </button>
        </div>
      </div>
      <ErrorBanner error={resource.error} onRetry={resource.reload} />
      <div className="workspace-scope" data-tour="workspace-scope">
        <span className="row gap8">
          <span className="live-dot" />
          Updates every 5 seconds
        </span>
        <label>
          Case scope{" "}
          <select
            aria-label="Case scope"
            value={scope}
            onChange={(e) => {
              setScope(e.target.value);
              if (e.target.value === "all") activeResource.reload();
            }}
          >
            <option value="active">Current practice session</option>
            <option value="all">All accessible demo cases</option>
          </select>
        </label>
      </div>
      <div className="kpis" data-tour="kpis">
        <Card className="kpi">
          <div className="row">
            <span className="muted">Confirmed disputed</span>
            <Badge tone="outline">Bank matched</Badge>
          </div>
          <div className="v num">
            {resource.data
              ? formatMinor(
                  all.reduce(
                    (v, c) => v + (c.confirmed_disputed_minor || 0),
                    0,
                  ),
                )
              : "—"}
          </div>
          <small>
            {counts?.total ?? "—"} cases in this scope · candidates excluded
          </small>
        </Card>
        <Card className="kpi hot">
          <div className="row">
            <span className="muted">Golden-hour priority</span>
            <Clock size={15} />
          </div>
          <div className="v num">
            {counts?.urgent ?? "—"}
            <span className="kpi-unit">cases need prompt attention</span>
          </div>
          <div className="priority-track">
            {all
              .filter((c) => (c.clock?.golden_hour_remaining || 0) > 0)
              .map((c) => (
                <i
                  key={c.case_id}
                  title={c.case_id}
                  style={{
                    left: `${Math.max(0, Math.min(98, 100 - (c.clock.golden_hour_remaining / 60) * 100))}%`,
                  }}
                />
              ))}
          </div>
          <small>Response priority · no recovery guarantee</small>
        </Card>
        <Card className="kpi">
          <div className="row">
            <span className="muted">Awaiting clarification</span>
            <FileText size={15} />
          </div>
          <div className="v num">{counts?.awaiting_information ?? "—"}</div>
          <small>Focused questions sent to the customer</small>
        </Card>
        <Card className="kpi">
          <div className="row">
            <span className="muted">Ready for review</span>
            <Activity size={15} />
          </div>
          <div className="v num">{counts?.ready_for_review ?? "—"}</div>
          <small>Evidence-backed reviewer decision required</small>
        </Card>
      </div>
      <div className="command-grid">
        <Card className="queue-card" data-tour="case-queue">
          <CardH
            title={
              <>
                Case queue <Badge tone="outline">{rows.length} cases</Badge>
              </>
            }
            sub={
              resource.updated
                ? "Updated " + time(resource.updated)
                : "Loading current records"
            }
          >
            <label className="search">
              <Search size={14} />
              <input
                aria-label="Filter cases"
                placeholder="Search case or account…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </label>
          </CardH>
          <div className="queue-filters">
            {[
              ["all", "All cases"],
              ["processing", "Processing"],
              ["awaiting_information", "Awaiting information"],
              ["ready_for_review", "Review ready"],
            ].map(([id, name]) => (
              <button
                key={id}
                className={"btn sm " + (filter === id ? "dark" : "ghost")}
                onClick={() => setFilter(id)}
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
                    <th>Case / customer account</th>
                    <th>Disputed amount</th>
                    <th>Response window</th>
                    <th>State / next step</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((c) => (
                    <tr key={c.case_id}>
                      <td>
                        <div className="row gap10">
                          <span className="avatar">
                            {c.customer_account?.slice(-2) || "CP"}
                          </span>
                          <div>
                            <button
                              className="case-link"
                              onClick={() => open(c)}
                            >
                              {c.case_id}
                              <ArrowRight size={12} />
                            </button>
                            <small className="mono muted">
                              {c.customer_account}
                            </small>
                            <small className="muted">
                              {label(c.intake_channel)} · {time(c.reported_at)}
                            </small>
                          </div>
                        </div>
                      </td>
                      <td>
                        <b className="num">
                          {formatMinor(c.confirmed_disputed_minor)}
                        </b>
                        <small className="muted">
                          {formatMinor(c.additional_candidate_minor)} candidate
                        </small>
                      </td>
                      <td>
                        <span className="mono warn-text">
                          {remaining(c.clock?.golden_hour_remaining)}
                        </span>
                        <div className="bar">
                          <i
                            style={{
                              width: `${Math.min(100, Math.max(0, ((c.clock?.golden_hour_remaining || 0) / 60) * 100))}%`,
                              background: "var(--warn)",
                            }}
                          />
                        </div>
                      </td>
                      <td>
                        <Status value={c.status} />
                        <small className="queue-next">
                          {c.brief?.recommended_action?.action ||
                            label(c.unresolved?.[0] || "Inspect assessment")}
                        </small>
                        <small className="muted">
                          Owner: {label(c.followup?.owner || "Unassigned")}
                        </small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!rows.length && (
                <div className="queue-empty">
                  <Inbox size={30} />
                  <h3>
                    {q || filter !== "all"
                      ? "No matching cases"
                      : "No complaints in this practice session"}
                  </h3>
                  <p>
                    {q || filter !== "all"
                      ? "Change the search or status filter to see other cases."
                      : "Bank data is prepared. Submit a report through the victim portal; it will appear here automatically."}
                  </p>
                  <div className="row gap8">
                    <button
                      className="btn primary"
                      onClick={() => go("/victim/start")}
                    >
                      Open reporting portal
                    </button>
                    {scope === "active" && (
                      <button
                        className="btn"
                        onClick={() => {
                          setScope("all");
                          activeResource.reload();
                        }}
                      >
                        View preserved cases
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
          <div className="queue-foot">
            {rows.length} cases shown · response priority order
            <span>Select a case to inspect its investigation brief.</span>
          </div>
        </Card>
        <aside className="col gap14">
          <Card>
            <CardH
              title="Live signals"
              sub="Current workflow records"
              icon={<Activity size={15} />}
            />
            <div className="signals-list">
              {!all.length ? (
                <Empty>
                  New complaints and processing changes appear here when
                  received.
                </Empty>
              ) : (
                all.slice(0, 5).map((c) => (
                  <button
                    className="signal actual-signal"
                    key={c.case_id}
                    onClick={() => open(c)}
                  >
                    <span className="signal-pip" />
                    <div className="grow">
                      <b>{label(c.status)}</b>
                      <small className="mono">{c.case_id}</small>
                      <small>
                        {c.brief?.recommended_action?.action ||
                          "Review current evidence"}
                      </small>
                    </div>
                  </button>
                ))
              )}
            </div>
          </Card>
          <Card>
            <CardH
              title="Next case to inspect"
              sub="First in the backend queue"
            />
            {next ? (
              <div className="card-b next-case">
                <b className="mono">{next.case_id}</b>
                <h2>{formatMinor(next.confirmed_disputed_minor)}</h2>
                <p>
                  {next.brief?.summary ||
                    next.victim_summary ||
                    "Assessment is pending."}
                </p>
                <button className="btn primary full" onClick={() => open(next)}>
                  Open investigation
                  <ArrowRight size={14} />
                </button>
              </div>
            ) : (
              <div className="card-b">
                <h3>Ready for the next report</h3>
                <p className="muted">
                  The queue starts empty for a fresh practice session. Submitted
                  complaints stay preserved across reloads.
                </p>
              </div>
            )}
          </Card>
          <Card className="card-b">
            <b>Investigation first</b>
            <p className="muted">
              Inspect the brief and its sources. Use the justified first action;
              urgent referral and complete documentation have separate review
              gates.
            </p>
          </Card>
        </aside>
      </div>
    </div>
  );
}
