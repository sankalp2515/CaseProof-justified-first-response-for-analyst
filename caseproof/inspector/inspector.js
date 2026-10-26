let snapshot = null,
  workflow = null,
  workspace = { cases: [], counts: {} };
let previousRevision = null,
  selectedTab = "overview",
  loading = false,
  pending = false;
let selectedEvidence = null,
  highlighted = [],
  routeEpoch = 0,
  confirmTask = null;
const links = new Map();
const packetCache = new Map();
const $ = (id) => document.getElementById(id);
const money = (value) =>
  value === null || value === undefined
    ? "Not established"
    : new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
      }).format(value / 100);
const labels = {
  new: "New complaint",
  processing: "Processing evidence",
  needs_analysis: "Analysis needed",
  needs_attention: "Needs information",
  awaiting_information: "Waiting for customer",
  ready_for_review: "Ready for review",
  approved: "Approved",
  completed: "Reports delivered",
  failed: "Processing failed",
  COMPLETE_CANDIDATE: "Complete candidate",
  REVIEW_REQUIRED: "More information needed",
  ESCALATE_CANDIDATE: "Escalation candidate",
  source_supported: "Source supported",
  reported: "Reported",
  unresolved: "Not verified",
  conflicted: "Conflicting evidence",
  proposed: "Suggested",
  accepted: "Sent to customer",
  fulfilled: "Response received",
  unavailable: "Unavailable",
  suppressed: "Not needed",
  skipped: "Skipped",
  blocked: "Blocked",
};
const factNames = {
  amount: "Payment amount",
  date: "Payment date and time",
  txn_datetime: "Payment date and time",
  transaction_reference: "Payment reference",
  deception_account: "Account of what happened",
  all_transfers_accounted: "Account for candidate disputed payments",
  payee_vpa: "Payee",
  caller_number: "Reported caller",
  scam_instruction: "Reported instructions",
  customer_statement: "Customer statement",
  currency: "Currency",
  readable_receipt: "Readable receipt",
  receipt_association: "Identify which payment the receipt describes",
  bank_verified: "Bank transaction verification (bank-side)",
  bank_data_refresh: "Refresh expired bank data (bank-side)",
  ledger_coverage:
    "Complete bank debit history for the complaint window (bank-side)",
};
const eventNames = {
  artifact_added: "Evidence received",
  processed: "Analysis and verification completed",
  request_accepted: "Information request prepared",
  customer_link_issued: "Customer link created",
  request_fulfilled: "Customer response received",
  request_unavailable: "Customer cannot provide evidence",
  request_skipped: "Request skipped",
  approved: "Reviewer decision recorded",
  claim_corrected: "Fact correction recorded",
  local_replay_clock: "Synthetic replay time selected",
};
function element(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function clear(id) {
  $(id).replaceChildren();
}
function state(value) {
  return element(
    "span",
    labels[value] || value.replaceAll("_", " "),
    "state " + value,
  );
}
function status(message, error = false) {
  $("status").hidden = !message;
  $("status").textContent = message;
  $("status").className = "notice" + (error ? " error" : "");
}
function friendly(error) {
  const value = String(error.message || error);
  if (value.includes("stale_bank_data"))
    return "Bank data has expired. Refresh the bank data and run analysis again before approving or sending.";
  if (
    value.includes("409") ||
    /stale|approval_required|payload_changed/.test(value)
  )
    return "This case changed or needs a current approval. Review the latest evidence and approve again before sending.";
  if (/403|access denied/.test(value))
    return "This action is not available for your demo role. Use Analyst to collect evidence or Reviewer to record a decision.";
  if (/422|invalid action/.test(value))
    return "The action could not be completed. Check the required fields and current case status, then try again.";
  if (/Failed to fetch|NetworkError|502|503|504/.test(value))
    return "The local service could not be reached. Check that the Docker services are running, then refresh.";
  return value;
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "X-Demo-User": $("role").value,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw Error(String(response.status) + " Local service unavailable");
  }
  if (!response.ok)
    throw Error(
      String(response.status) +
        " " +
        (data.error || data.detail || "Request failed"),
    );
  return data;
}
async function perform(button, work) {
  if (pending) return;
  const epoch = routeEpoch;
  pending = true;
  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Working…";
  button.setAttribute("aria-busy", "true");
  try {
    await work(epoch);
  } catch (error) {
    if (epoch === routeEpoch) {
      status(friendly(error), true);
      if (snapshot && !$("case-page").hidden)
        await loadCase(snapshot.case_id, false, epoch).catch(() => {});
    }
  } finally {
    pending = false;
    button.textContent = original;
    button.disabled = false;
    button.removeAttribute("aria-busy");
    controls();
  }
}
function empty(parent, title, detail) {
  const box = element("div", undefined, "empty");
  box.append(element("strong", title), element("p", detail));
  parent.append(box);
}
function nextText(row) {
  if (row.bank_data_refresh_required)
    return "Bank observations need refreshing. Background bank services will retry; review internal verification rather than requesting bank data from the victim.";
  if (row.historical_deliveries?.length && row.status === "ready_for_review")
    return "Earlier reports were delivered. Review the new assessment before deciding whether another report update is needed.";
  return {
    new: "Share a private evidence link with the customer.",
    processing:
      "Analysis runs automatically. This view updates when it finishes.",
    needs_analysis:
      "Submit the customer response, or analyze the evidence already received.",
    needs_attention: "Review missing information and send one focused request.",
    awaiting_information:
      "The customer has an outstanding information request.",
    ready_for_review:
      row.readiness === "ESCALATE_CANDIDATE"
        ? "Review the gaps and approve an escalation."
        : "Check the sources, then ask a reviewer to approve.",
    approved:
      "Send the approved report and case packet to the local simulators.",
    completed:
      "Both simulated destinations acknowledged this revision. Track the receiving institution’s outcome; the investigation remains open.",
    failed: "Processing stopped safely. Review the error and retry.",
  }[row.status];
}
async function refreshWorkspace() {
  workspace = await api(
    "/v1/workspace?scope=" +
      (new URLSearchParams(location.search).get("operator") === "1"
        ? "all"
        : "active"),
  );
  $("case-count").textContent = workspace.counts.total || 0;
  renderDashboard();
  renderCases();
  controls();
}
function renderDashboard() {
  $("metrics").setAttribute("aria-busy", "false");
  clear("metrics");
  const metrics = [
    ["total", "Total cases"],
    ["new", "New complaints"],
    ["urgent", "Within golden hour"],
    ["awaiting_information", "Waiting for customer"],
    ["ready_for_review", "Ready for review"],
    ["completed", "Reports delivered"],
  ];
  for (const [key, label] of metrics) {
    const button = element("button", undefined, "metric");
    button.append(
      element("strong", workspace.counts[key] || 0),
      element("span", label),
    );
    button.onclick = () => {
      $("case-filter").value = key === "total" ? "all" : key;
      $("case-search").value = "";
      location.hash = "cases";
      renderCases();
    };
    $("metrics").append(button);
  }
  clear("attention-list");
  const active = workspace.cases
    .filter((r) => r.status !== "completed")
    .slice(0, 6);
  if (active.length) $("attention-list").append(caseTable(active));
  else
    empty(
      $("attention-list"),
      workspace.cases.length ? "No open work" : "Your workspace is ready",
      "Open the victim reporting portal to create a new complaint. Each case is processed from the submitted evidence and independent bank records.",
    );
}
function caseTable(rows) {
  const wrap = element("div", undefined, "case-table"),
    table = element("table");
  const head = element("thead"),
    hr = element("tr");
  for (const label of [
    "Complaint",
    "Status",
    "Amount",
    "Golden hour",
    "Next step",
  ])
    hr.append(element("th", label));
  head.append(hr);
  table.append(head);
  const body = element("tbody");
  for (const row of rows) {
    const tr = element("tr"),
      cell = element("td"),
      open = element("button", row.case_id, "case-link");
    open.onclick = () => {
      location.hash = "case=" + encodeURIComponent(row.case_id);
    };
    cell.append(
      open,
      element("small", row.customer_account || "Customer account not provided"),
    );
    const statusCell = element("td");
    statusCell.append(state(row.status));
    const clock = row.clock.golden_hour_remaining;
    const time =
      clock === null
        ? "Time unknown"
        : clock > 0
          ? clock.toFixed(1) + " min left"
          : "Window elapsed";
    const timeCell = element("td", time);
    timeCell.title =
      row.position_reason + "; prioritisation heuristic, not a legal deadline";
    if (row.clock.replay) timeCell.append(element("small", "Replay time"));
    tr.append(
      cell,
      statusCell,
      element("td", money(row.amount_minor)),
      timeCell,
      element("td", nextText(row)),
    );
    body.append(tr);
  }
  table.append(body);
  wrap.append(table);
  return wrap;
}
function renderCases() {
  clear("case-list");
  const term = $("case-search").value.trim().toLowerCase(),
    filter = $("case-filter").value;
  const rows = workspace.cases.filter(
    (r) =>
      (filter === "all" ||
        r.status === filter ||
        (filter === "urgent" &&
          r.clock.golden_hour_remaining > 0 &&
          r.status !== "completed") ||
        (filter === "needs_attention" && r.status === "needs_analysis")) &&
      (r.case_id + " " + r.customer_account).toLowerCase().includes(term),
  );
  $("list-count").textContent =
    rows.length + " of " + workspace.cases.length + " cases";
  if (rows.length) $("case-list").append(caseTable(rows));
  else
    empty(
      $("case-list"),
      "No matching cases",
      "Clear the search or choose another status. Open a complaint to start a new case.",
    );
}
function showPage(name) {
  for (const view of ["dashboard", "cases", "case"])
    $(view + "-page").hidden = view !== name;
  $("dashboard-tab").classList.toggle("active", name === "dashboard");
  $("queue-tab").classList.toggle("active", name !== "dashboard");
}
function showTab(name, updateHash = true) {
  if (
    !["overview", "evidence", "verification", "review", "activity"].includes(
      name,
    )
  )
    name = "overview";
  selectedTab = name;
  for (const button of document.querySelectorAll("[data-tab]")) {
    const selected = button.dataset.tab === name;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
    $("tab-" + button.dataset.tab).hidden = !selected;
  }
  if (snapshot && updateHash)
    history.replaceState(
      null,
      "",
      "#case=" + encodeURIComponent(snapshot.case_id) + "&view=" + name,
    );
}
async function route() {
  const epoch = ++routeEpoch;
  try {
    const hash = location.hash.slice(1);
    if (hash.startsWith("case=")) {
      const params = new URLSearchParams(hash);
      selectedTab = params.get("view") || "overview";
      await loadCase(params.get("case"), true, epoch);
    } else {
      showPage(hash === "cases" ? "cases" : "dashboard");
      if (!pending) status("Loading cases…");
      await refreshWorkspace();
      if (!pending) status("");
      if (hash.startsWith("new-complaint=") && epoch === routeEpoch) {
        const params = new URLSearchParams(hash);
        openComplaint();
        $("create-account").value = params.get("new-complaint") || "";
        for (const [field, key] of [
          ["create-reported", "reported"],
          ["create-contact", "contact"],
        ]) {
          const date = new Date(params.get(key));
          if (!Number.isNaN(date.getTime()))
            $(field).value = new Date(
              date.getTime() - date.getTimezoneOffset() * 60000,
            )
              .toISOString()
              .slice(0, 16);
        }
      }
    }
  } catch (error) {
    status(friendly(error), true);
  }
}
async function loadCase(id, announce = false, epoch = routeEpoch, attempt = 0) {
  if (announce && attempt === 0) status("Loading complaint…");
  const [data, flow, audit, preview] = await Promise.all([
    api("/v1/cases/" + encodeURIComponent(id)),
    api("/v1/cases/" + encodeURIComponent(id) + "/workflow"),
    api("/v1/cases/" + encodeURIComponent(id) + "/audit"),
    api("/v1/cases/" + encodeURIComponent(id) + "/report-preview"),
  ]);
  if (epoch !== routeEpoch) return;
  // A concurrent worker may publish between reads. Never mix revisions in review controls.
  if (
    data.revision !== flow.revision ||
    data.digest !== flow.digest ||
    preview.revision !== data.revision
  )
    if (attempt < 3) return loadCase(id, announce, epoch, attempt + 1);
    else
      throw Error(
        "This case is updating. Wait a moment, then refresh to review a consistent revision.",
      );
  const changedCase = snapshot?.case_id !== id;
  if (changedCase || snapshot.revision !== data.revision) {
    $("change-summary").replaceChildren();
    $("diff-result").textContent = "";
    $("diff-result").hidden = true;
    $("diff-details").hidden = true;
    $("diff-details").open = false;
  }
  if (!changedCase && snapshot.revision !== data.revision)
    previousRevision = snapshot.revision;
  if (changedCase) {
    previousRevision = null;
    selectedEvidence = null;
    highlighted = [];
    $("reason").value = "";
  }
  snapshot = data;
  workflow = flow;
  if (links.has(id) && data.revision > links.get(id).revision) links.delete(id);
  render();
  renderActivity(audit);
  $("preview").textContent = JSON.stringify(preview, null, 2);
  const unmatched = (preview.evidence_only_debits || []).reduce(
    (sum, d) => sum + d.amount_minor,
    0,
  );
  if (unmatched)
    $("trail-totals").textContent +=
      " · " + money(unmatched) + " reported in receipts, not yet bank-matched";
  showPage("case");
  showTab(selectedTab, false);
  if (announce) status("Case opened. " + nextText(flow));
}
function render() {
  const s = snapshot,
    w = workflow;
  $("case-name").textContent = s.case_id.startsWith("GOLD-001")
    ? "Ananya’s complaint"
    : "Complaint workspace";
  $("case-id").textContent = s.case_id;
  if (w.overlapping_complaints?.length)
    $("case-id").textContent +=
      " · Possible overlapping complaint: " +
      w.overlapping_complaints.join(", ");
  $("revision").textContent =
    "Revision " + s.revision + " / digest " + s.digest;
  $("case-status").replaceChildren(state(w.status));
  $("clock-left").textContent =
    w.clock.golden_hour_remaining === null
      ? "Debit time unknown"
      : w.clock.golden_hour_remaining > 0
        ? w.clock.golden_hour_remaining.toFixed(1) + " min remaining"
        : "Golden-hour window elapsed";
  $("clock-note").textContent =
    (w.clock.replay ? "Replay clock · " : "Last evaluated · ") +
    new Date(w.clock.as_of).toLocaleString();
  renderProgress();
  renderNext();
  renderUrgent();
  clear("case-overview");
  renderBrief();
  renderFollowup();
  const items = [
    [
      "Victim’s account of the incident",
      w.victim_summary || "Awaiting the victim’s account",
      "Reported information; bank verification is shown separately",
    ],
    [
      w.amount_basis === "bank_records"
        ? "Confirmed disputed payments"
        : "Reported amount",
      money(
        w.amount_basis === "bank_records"
          ? w.confirmed_disputed_minor
          : w.amount_minor,
      ),
      w.amount_basis === "bank_records"
        ? "From simulated bank records"
        : "Not bank confirmed; not a sum of payments",
    ],
    [
      "Additional payments awaiting confirmation",
      money(w.additional_candidate_minor),
      "Not included in confirmed disputed loss",
    ],
    [
      "Customer account",
      w.customer_account || "Not provided",
      w.intake_channel === "bank_website"
        ? "Customer identified through bank reporting portal"
        : "Employee-assisted complaint",
    ],
    [
      "Evidence received",
      String(s.artifacts.length) + " files / responses",
      String(s.facts.length) + " extracted facts",
    ],
    [
      "Reported",
      w.reported_at ? new Date(w.reported_at).toLocaleString() : "Not provided",
      "Revision " + s.revision,
    ],
  ];
  for (const [label, value, note] of items) {
    const box = element("div", undefined, "overview-item");
    box.append(
      element("span", label),
      element("strong", value),
      element("small", note),
    );
    $("case-overview").append(box);
  }
  clear("artifacts");
  for (const a of s.artifacts) {
    const option = element(
      "option",
      a.kind.replaceAll("_", " ") + " · " + a.stage,
    );
    option.value = a.artifact_id;
    $("artifacts").append(option);
  }
  clear("facts");
  $("fact-count").textContent =
    s.facts.length + " facts from " + s.claims.length + " observations";
  if (!s.facts.length)
    empty(
      $("facts"),
      "No facts extracted yet",
      w.status === "processing"
        ? "Analysis is running automatically."
        : "Collect evidence from the customer to begin.",
    );
  for (const fact of s.facts) {
    const row = element("div", undefined, "fact");
    row.append(
      element(
        "strong",
        (factNames[fact.kind] || fact.kind.replaceAll("_", " ")) +
          ": " +
          (fact.kind === "amount" ? money(fact.value) : String(fact.value)),
      ),
    );
    for (const st of fact.states) row.append(state(st));
    const chips = element("div");
    for (const id of fact.sources) {
      const seg = s.segments.find((x) => x.segment_id === id);
      const artifact =
        seg && s.artifacts.find((a) => a.artifact_id === seg.artifact_id);
      if (!artifact) continue;
      const chip = element(
        "button",
        artifact.kind.replaceAll("_", " ") +
          " · line " +
          (Number(id.split("-").pop()) + 1),
        "source-chip",
      );
      chip.onclick = () => {
        selectedEvidence = seg.artifact_id;
        highlighted = [id];
        showEvidence(selectedEvidence, highlighted);
      };
      chips.append(chip);
    }
    row.append(chips);
    $("facts").append(row);
  }
  const artifact =
    s.artifacts.find((a) => a.artifact_id === selectedEvidence) ||
    s.artifacts.find((a) => a.kind === "receipt") ||
    s.artifacts[0];
  if (artifact) {
    selectedEvidence = artifact.artifact_id;
    showEvidence(selectedEvidence, highlighted);
  } else {
    clear("boxes");
    $("evidence-image").removeAttribute("src");
    $("canvas").style.display = "none";
    $("evidence-text").hidden = false;
    $("evidence-text").textContent =
      "No evidence received. Share a private customer link from Overview.";
    $("source-note").textContent = "";
  }
  renderVerification();
  renderRequests();
  controls();
  $("runs").textContent = JSON.stringify(s.run_meta, null, 2);
  $("raw-claims").textContent = JSON.stringify(s.claims, null, 2);
  const link = links.get(s.case_id);
  $("customer-link-box").hidden = !link;
  if (link) $("customer-link").href = link.url;
}
function renderProgress() {
  clear("workflow-progress");
  const s = snapshot,
    w = workflow,
    active = w.status === "processing",
    failed = w.status === "failed";
  const steps = [
    [
      "Evidence",
      s.artifacts.length ? "Received" : "Not started",
      s.artifacts.length ? "done" : "current",
    ],
    [
      "Analysis",
      failed
        ? "Failed"
        : active
          ? "Processing"
          : s.segments.length
            ? "Completed"
            : "Not started",
      failed
        ? "attention"
        : active
          ? "current"
          : s.segments.length
            ? "done"
            : "",
    ],
    [
      "Verification",
      s.ledger_matches.length
        ? "Bank match found"
        : s.segments.length
          ? "Needs attention"
          : "Not started",
      s.ledger_matches.length ? "done" : s.segments.length ? "attention" : "",
    ],
    [
      "Human review",
      w.approval
        ? "Approved"
        : w.status === "ready_for_review"
          ? "Ready for review"
          : "Requirements pending",
      w.approval ? "done" : w.status === "ready_for_review" ? "current" : "",
    ],
    [
      "Simulated handoff",
      w.status === "completed"
        ? "Delivered"
        : w.approval
          ? "Ready to send"
          : "Not started",
      w.status === "completed" ? "done" : w.approval ? "current" : "",
    ],
  ];
  for (const [name, detail, cls] of steps) {
    const item = element("li", name, cls);
    item.append(element("small", detail));
    $("workflow-progress").append(item);
  }
}
function renderNext() {
  clear("next-step");
  const w = workflow,
    copy = element("div");
  copy.append(element("h2", labels[w.status]), element("p", nextText(w)));
  $("next-step").append(copy);
  const action = (label, fn) => {
    const b = element("button", label);
    b.onclick = fn;
    if (["new", "needs_analysis", "failed"].includes(w.status)) {
      b.dataset.analystAction = "true";
      b.disabled = pending || $("role").value === "reviewer";
      if ($("role").value === "reviewer")
        b.title = "Use the Analyst demo role to collect or process evidence.";
    }
    $("next-step").append(b);
  };
  if (w.status === "new")
    action("Collect customer evidence", () => {
      showTab("overview");
      $("upload-link").click();
    });
  else if (w.status === "needs_analysis")
    action("Analyze evidence", () =>
      perform($("next-step").querySelector("button"), async (epoch) => {
        const cid = snapshot.case_id;
        await api("/v1/cases/" + cid + "/process", {
          method: "POST",
        });
        await loadCase(cid, false, epoch);
        if (epoch !== routeEpoch) return;
        status(
          "Evidence queued for analysis. You can stay on this case; it will update automatically.",
        );
      }),
    );
  else if (w.status === "failed" && w.job) {
    copy.append(
      element(
        "p",
        w.job.error === "LOCAL_OCR_ERROR"
          ? "The local OCR service could not read the evidence. Restore the service, then retry."
          : "Analysis failed: " + (w.job.error || "Unknown processing error"),
      ),
    );
    action("Retry analysis", () =>
      perform($("next-step").querySelector("button"), async (epoch) => {
        const cid = snapshot.case_id;
        await api("/v1/jobs/" + w.job.job_id + "/retry", { method: "POST" });
        await loadCase(cid, false, epoch);
        if (epoch !== routeEpoch) return;
        status("Analysis queued again. Existing evidence has been preserved.");
      }),
    );
  } else if (["approved", "ready_for_review"].includes(w.status))
    action("Review & decision", () => showTab("review"));
  else if (w.bank_data_refresh_required)
    action("Review bank verification", () => showTab("verification"));
  else if (w.status === "needs_attention")
    action("Review missing information", () => {
      showTab("overview");
      $("requests").scrollIntoView({ block: "center", behavior: "smooth" });
    });
}

async function renderUrgent() {
  const cid = snapshot.case_id,
    epoch = routeEpoch;
  $("urgent-panel").hidden = false;
  $("report-history").replaceChildren();
  for (const row of workflow.historical_deliveries || []) {
    const p = element(
      "p",
      (row.kind === "case_ticket" ? "Bank case packet" : "CFCFRMS update") +
        " · revision " +
        row.revision +
        " · acknowledged",
    );
    if (row.kind === "case_ticket" && row.packet_id) {
      const link = element("a", "View delivered packet");
      link.href =
        "/v1/cases/" +
        cid +
        "/delivered-packets/" +
        encodeURIComponent(row.packet_id);
      link.target = "_blank";
      link.rel = "noopener";
      p.append(document.createTextNode(" · "), link);
    }
    $("report-history").append(p);
  }
  $("urgent-note").textContent = workflow.urgent_referral.reason;
  $("urgent-approve").disabled =
    !workflow.urgent_referral.eligible ||
    $("role").value === "analyst" ||
    pending;
  try {
    const rows = await api("/v1/cases/" + cid + "/urgent-referrals");
    if (epoch !== routeEpoch || snapshot.case_id !== cid) return;
    $("urgent-history").replaceChildren();
    for (const row of rows) {
      const p = element(
        "p",
        row.approval.approval_id +
          " · revision " +
          row.approval.revision +
          " · " +
          (row.delivery
            ? "Acknowledged by local simulator"
            : "Approved; not sent"),
      );
      if (!row.delivery && row.approval.revision === snapshot.revision) {
        const b = element("button", "Send approved urgent referral");
        b.disabled = $("role").value === "analyst";
        b.onclick = () =>
          perform(b, async () => {
            await api(
              "/v1/cases/" +
                cid +
                "/urgent-referrals/" +
                row.approval.approval_id +
                "/send",
              { method: "POST" },
            );
            await renderUrgent();
            status(
              "Urgent referral acknowledged by the local simulator. No hold is implied.",
            );
          });
        p.append(b);
      }
      $("urgent-history").append(p);
    }
  } catch (e) {
    status(friendly(e), true);
  }
}
$("urgent-approve").onclick = () => {
  if (!$("urgent-reason").value.trim()) {
    status("Enter the facts supporting this referral.", true);
    return;
  }
  const body = {
    expected_revision: snapshot.revision,
    digest: snapshot.digest,
    reason: $("urgent-reason").value,
  };
  perform($("urgent-approve"), async () => {
    await api("/v1/cases/" + snapshot.case_id + "/urgent-referrals", {
      method: "POST",
      body: JSON.stringify(body),
    });
    await renderUrgent();
    status("Urgent referral approved for this revision and transaction scope.");
  });
};
function renderVerification() {
  const s = snapshot,
    summary = s.trail?.summary || {};
  $("bank-note").textContent = s.ledger_matches.length
    ? s.ledger_matches.length +
      " transaction(s) matched with simulated bank records."
    : "No bank transaction has been matched. Customer statements alone are not bank confirmation.";
  $("bank-gap-actions").hidden =
    !s.artifacts.length ||
    !!workflow.approval ||
    !s.readiness.unresolved_facts.some((f) =>
      ["bank_verified", "ledger_coverage"].includes(f),
    );
  clear("ledger");
  clear("unreported");
  for (const m of s.ledger_matches) {
    const row = element("div", undefined, "record");
    row.append(
      element("strong", money(m.resolved_fields.amount) + " · " + m.txn_id),
      element(
        "small",
        "Reference: " +
          m.resolved_fields.transaction_reference +
          " · " +
          m.source,
      ),
      element(
        "small",
        new Date(m.resolved_fields.txn_datetime).toLocaleString() +
          " · " +
          m.resolved_fields.payee_vpa,
      ),
    );
    $("ledger").append(row);
  }
  for (const u of s.unreported) {
    const row = element(
      "p",
      "Additional debit needs confirmation: " +
        money(u.amount_minor) +
        " · " +
        u.txn_id,
      "reminder",
    );
    $("unreported").append(row);
  }
  $("linked").textContent =
    s.linked.length +
    " related complaints" +
    (s.linked.length
      ? ": " + s.linked.map((l) => l.complaint_id).join(", ")
      : ".");
  $("recoverable").textContent =
    money(workflow?.clock?.recoverable_now || 0) +
    " observed unspent in the model";
  $("trail-totals").textContent =
    money(summary.left_system || 0) +
    " left the modeled system · " +
    money(summary.unaccounted || 0) +
    " unaccounted for";
  clear("positions");
  clear("trail-sources");
  const groups = new Map();
  for (const p of s.trail?.positions || []) {
    if (!groups.has(p.account))
      groups.set(p.account, { amount: 0, status: p.status, paths: [] });
    const group = groups.get(p.account);
    group.amount += p.amount_minor;
    group.paths.push(p.path.join(" / "));
  }
  for (const [account, g] of groups) {
    const row = element("div", undefined, "location"),
      label = element("div", account);
    label.append(
      element(
        "small",
        g.status.replaceAll("_", " ") + " · " + g.paths.join("; "),
      ),
    );
    row.append(label, element("strong", money(g.amount)));
    $("positions").append(row);
  }
  if (!groups.size)
    empty(
      $("positions"),
      "No sourced money trail yet",
      "A verified bank root and downstream observations are needed. No recovery amount is inferred from a customer statement.",
    );
  for (const t of s.trail?.transfers || [])
    $("trail-sources").append(
      element("p", t.txn_id + " · " + t.source + " · " + money(t.amount_minor)),
    );
  for (const a of s.trail?.account_observations || [])
    $("trail-sources").append(
      element(
        "p",
        a.account +
          " · " +
          a.reporting_bank +
          " · observed balance " +
          money(a.balance_minor) +
          " · " +
          a.update_id +
          " · " +
          (a.freshness?.state || "freshness not evaluated") +
          (a.reported_at
            ? " · reported " + new Date(a.reported_at).toLocaleString()
            : ""),
      ),
    );
  for (const debit of s.trail?.debit_clocks || [])
    $("trail-sources").append(
      element(
        "p",
        debit.txn_id +
          " · " +
          money(debit.amount_minor) +
          " · debit " +
          new Date(debit.ts).toLocaleString() +
          " · " +
          debit.basis.replaceAll("_", " ") +
          (debit.time_status === "future" ? " · future time needs review" : ""),
      ),
    );
  drawTrail();
}
function renderRequests() {
  clear("requests");
  clear("skipped");
  const accepted = snapshot.requests.find((r) => r.state === "accepted");
  const current =
    accepted || snapshot.requests.find((r) => r.state === "proposed");
  const gaps = snapshot.readiness.unresolved_facts;
  $("missing-note").textContent =
    workflow.status === "new"
      ? "Collect the initial evidence to see what is missing."
      : gaps.length
        ? "Still needed: " +
          gaps.map((x) => factNames[x] || x.replaceAll("_", " ")).join(", ") +
          "."
        : workflow.status === "processing"
          ? "Analysis is running. Requirements will update when it finishes."
          : "No required facts are currently missing. Human review is a separate step.";
  for (const r of snapshot.requests) {
    const box = element("div", undefined, "request");
    box.append(element("strong", r.reason), state(r.state));
    if (r === current) {
      box.append(
        element(
          "p",
          accepted
            ? "Waiting for the customer's response. Recreating this request link replaces its previous link."
            : "This request addresses the highest-ranked information gap.",
        ),
        element("p", r.reminder, "reminder"),
      );
      const send = element(
        "button",
        accepted ? "Recreate customer request link" : "Request information",
      );
      send.disabled = $("role").value === "reviewer" || pending;
      send.dataset.analystAction = "true";
      send.onclick = () =>
        perform(send, async (epoch) => {
          const cid = snapshot.case_id;
          const result = await api(
            "/v1/cases/" + cid + "/requests/" + r.request_id + "/send",
            { method: "POST" },
          );
          links.set(cid, result);
          await loadCase(cid, false, epoch);
          if (epoch !== routeEpoch) return;
          status(
            "Request link created. Share it with the customer; delivery by SMS is simulated.",
          );
        });
      box.append(send);
      $("requests").append(box);
    } else {
      box.append(
        element(
          "p",
          "Can address: " +
            r.explanation.can_settle.map((x) => factNames[x] || x).join(", ") +
            " · catalogue score " +
            r.score,
        ),
      );
      $("skipped").append(box);
    }
  }
  if (!current)
    $("requests").append(
      element(
        "p",
        "No customer request is pending. " +
          (gaps.length
            ? "The case still needs review of the listed gaps."
            : workflow.status === "completed"
              ? "See Review & decision for the delivery record."
              : "Continue to review when analysis is complete."),
        "muted",
      ),
    );
}
function controls() {
  if (workflow)
    $("urgent-approve").disabled =
      pending ||
      $("role").value === "analyst" ||
      !workflow.urgent_referral.eligible;
  $("bank-gap-unavailable").disabled =
    pending || $("role").value === "reviewer";
  for (const button of document.querySelectorAll("[data-analyst-action]"))
    button.disabled = pending || $("role").value === "reviewer";
  $("new-case").disabled = $("role").value === "reviewer";
  $("demo-case").disabled = pending || $("role").value === "reviewer";
  $("start-complaint").disabled = $("role").value === "reviewer";
  if (!snapshot || !workflow) return;
  const reviewer = $("role").value !== "analyst",
    ready = ["COMPLETE_CANDIDATE", "ESCALATE_CANDIDATE"].includes(
      workflow.readiness,
    );
  $("readiness").replaceChildren(state(workflow.readiness));
  $("review-note").textContent = workflow.bank_data_refresh_required
    ? "Bank observations are missing or expired. Background bank services will retry. Review the new revision when fresh data arrives; contact bank data operations if unavailable."
    : workflow.approval
      ? "A reviewer approved this exact revision. New evidence requires a new review."
      : ready
        ? "Evidence requirements permit a human decision. Review the sources before approving."
        : "A decision is unavailable until the required information is supported or the case is eligible for escalation.";
  $("approve").textContent =
    snapshot.readiness.disposition === "ESCALATE_CANDIDATE"
      ? "Approve escalation"
      : "Approve case";
  $("approve").disabled =
    pending ||
    !reviewer ||
    !ready ||
    !!workflow.approval ||
    workflow.status === "processing";
  $("export").disabled =
    pending ||
    !reviewer ||
    !workflow.approval ||
    !!workflow.bank_data_refresh_required;
  $("export").textContent =
    workflow.status === "completed"
      ? "View delivered packet"
      : "Send simulated reports";
  $("upload-link").disabled = pending || $("role").value === "reviewer";
  $("new-case").disabled = $("role").value === "reviewer";
  $("demo-case").disabled = pending || $("role").value === "reviewer";
  $("start-complaint").disabled = $("role").value === "reviewer";
  $("decision-help").textContent = !reviewer
    ? "Use the Reviewer demo role to record a decision. Analysts collect and check evidence."
    : !ready
      ? "Resolve the listed requirements, or record unavailable information through the customer request."
      : workflow.approval
        ? "Approved revision " +
          workflow.approval.revision +
          ". Sending is simulated and can be retried without duplicating acknowledged deliveries."
        : "Enter a review reason. You will confirm the decision before it is recorded.";
  clear("requirements");
  for (const fact of snapshot.readiness.unresolved_facts)
    $("requirements").append(
      element(
        "li",
        "Needed: " + (factNames[fact] || fact.replaceAll("_", " ")),
      ),
    );
  for (const conflict of snapshot.readiness.blocking_conflicts)
    $("requirements").append(
      element("li", "Conflicting evidence: " + conflict),
    );
  if (
    !snapshot.readiness.unresolved_facts.length &&
    !snapshot.readiness.blocking_conflicts.length
  )
    $("requirements").append(
      element(
        "li",
        snapshot.segments.length
          ? "No unresolved requirements recorded."
          : "Initial evidence has not been analyzed.",
      ),
    );
  clear("delivery-result");
  for (const d of workflow.delivery_failures || [])
    $("delivery-result").append(
      element(
        "p",
        d.kind +
          " · " +
          d.status +
          " · Background delivery retries are bounded. Review current approval and retry sending if the receiver is restored.",
      ),
    );
  for (const d of workflow.deliveries)
    $("delivery-result").append(
      element(
        "p",
        (d.kind === "case_ticket" ? "Bank case packet" : "CFCFRMS update") +
          ": " +
          (d.status === "sent" ? "acknowledged by local simulator" : d.status) +
          (d.response?.message_id ? " · " + d.response.message_id : ""),
        "muted",
      ),
    );
  const cachedPacket = packetCache.get(snapshot.case_id);
  if (
    cachedPacket &&
    cachedPacket.approval_id === workflow.approval?.approval_id &&
    cachedPacket.revision === snapshot.revision
  ) {
    const download = element("button", "Download case packet", "secondary");
    download.onclick = () => {
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(cachedPacket, null, 2)], {
          type: "application/json",
        }),
      );
      const anchor = element("a");
      anchor.href = url;
      anchor.download = cachedPacket.packet_id + ".json";
      anchor.hidden = true;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    };
    $("delivery-result").append(download);
  }
  $("handoff-summary").replaceChildren(
    element("p", "Case: " + snapshot.case_id),
    element("p", "Amount: " + money(workflow.amount_minor)),
    element("p", "Bank matches: " + snapshot.ledger_matches.length),
    element(
      "p",
      "Additional debits awaiting confirmation: " + snapshot.unreported.length,
    ),
    element(
      "p",
      "Decision: " +
        (workflow.approval?.disposition?.replaceAll("_", " ") ||
          "Not recorded"),
    ),
  );
}
function renderActivity(events) {
  clear("activity");
  const first = element("li");
  first.append(
    element("strong", "Complaint opened"),
    element("small", "Initial case record · revision 1."),
  );
  $("activity").append(first);
  for (const event of events) {
    const row = element("li");
    row.append(
      element(
        "strong",
        eventNames[event.event] || event.event.replaceAll("_", " "),
      ),
      element(
        "small",
        new Date(event.at).toLocaleString() + " · revision " + event.revision,
      ),
    );
    $("activity").append(row);
  }
  for (const d of workflow.deliveries) {
    const row = element("li");
    row.append(
      element(
        "strong",
        (d.kind === "case_ticket" ? "Bank packet" : "CFCFRMS update") +
          (d.status === "sent"
            ? " delivered to simulator"
            : " awaiting delivery"),
      ),
      element("small", "Delivery record for the current approved revision."),
    );
    $("activity").append(row);
  }
}
async function showDiff() {
  const cid = snapshot.case_id,
    revision = snapshot.revision,
    epoch = routeEpoch;
  const from = previousRevision || Math.max(1, snapshot.revision - 1);
  const diff = await api(
    "/v1/cases/" + cid + "/revisions/" + from + "/diff/" + revision,
  );
  if (
    epoch !== routeEpoch ||
    snapshot.case_id !== cid ||
    snapshot.revision !== revision
  )
    return;
  $("diff-result").textContent = JSON.stringify(diff, null, 2);
  $("diff-result").hidden = false;
  $("diff-details").hidden = false;
  $("change-summary").textContent =
    "Comparing revision " +
    from +
    " with " +
    revision +
    ". " +
    (diff.added?.length || 0) +
    " added, " +
    (diff.removed?.length || 0) +
    " removed, " +
    (diff.changed?.length || 0) +
    " changed observations.";
  if (diff.readiness.before !== diff.readiness.after)
    $("change-summary").append(
      element(
        "p",
        "Readiness: " +
          labels[diff.readiness.before] +
          " → " +
          labels[diff.readiness.after] +
          ".",
      ),
    );
  const before = diff.money_trail?.before?.summary,
    after = diff.money_trail?.after?.summary;
  if (JSON.stringify(before) !== JSON.stringify(after))
    $("change-summary").append(
      element(
        "p",
        "Potentially recoverable: " +
          money(before?.recoverable || 0) +
          " → " +
          money(after?.recoverable || 0) +
          ". Unaccounted: " +
          money(after?.unaccounted || 0) +
          ".",
      ),
    );
}
function openConfirmation(title, text, actionLabel, task) {
  $("confirm-title").textContent = title;
  $("confirm-text").textContent = text;
  $("confirm-action").textContent = actionLabel;
  confirmTask = task;
  $("confirm-dialog").showModal();
}
function openComplaint() {
  const local = (date) =>
    new Date(date.getTime() - date.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 16);
  $("create-reported").value = local(new Date());
  $("create-contact").value = local(new Date(Date.now() - 3600000));
  $("create-error").textContent = "";
  $("create-dialog").showModal();
}
$("new-case").onclick = openComplaint;
$("start-complaint").onclick = openComplaint;
$("browse-cases").onclick = () => {
  $("case-filter").value = "all";
  $("case-search").value = "";
  location.hash = "cases";
};
$("case-search").oninput = renderCases;
$("case-filter").onchange = renderCases;
$("create-form").onsubmit = (event) => {
  event.preventDefault();
  perform($("create-submit"), async () => {
    if (!$("create-account").value.trim()) {
      $("create-error").textContent =
        "Enter the customer account to open a complaint.";
      return;
    }
    if (
      new Date($("create-contact").value) > new Date($("create-reported").value)
    ) {
      $("create-error").textContent =
        "First contact must be at or before the reporting time.";
      return;
    }
    const result = await api("/v1/cases", {
      method: "POST",
      body: JSON.stringify({
        customer_account: $("create-account").value.trim(),
        reported_at: new Date($("create-reported").value).toISOString(),
        first_contact: new Date($("create-contact").value).toISOString(),
      }),
    });
    $("create-dialog").close();
    location.hash = "case=" + encodeURIComponent(result.case_id);
    status(
      "Complaint opened. Next, create a private link so the customer can provide evidence.",
    );
    await refreshWorkspace();
  });
};
$("demo-case").hidden =
  new URLSearchParams(location.search).get("operator") !== "1";
$("demo-case").onclick = () =>
  perform($("demo-case"), async (epoch) => {
    status(
      "Creating a synthetic complaint. Local OCR and verification will run automatically.",
    );
    const result = await api("/v1/local/fixtures/GOLD-001", { method: "POST" });
    if (epoch !== routeEpoch) {
      await refreshWorkspace();
      return;
    }
    location.hash = "case=" + encodeURIComponent(result.case_id);
    await refreshWorkspace();
  });
$("upload-link").onclick = () =>
  perform($("upload-link"), async (epoch) => {
    const cid = snapshot.case_id,
      result = await api("/v1/cases/" + cid + "/upload-links", {
        method: "POST",
      });
    links.set(cid, result);
    await loadCase(cid, false, epoch);
    if (epoch !== routeEpoch) return;
    status(
      "Private evidence link created. Open or copy the link below. It expires in one hour.",
    );
  });
$("bank-gap-unavailable").onclick = () =>
  perform($("bank-gap-unavailable"), async (epoch) => {
    const reason = $("bank-gap-reason").value.trim();
    if (!reason) {
      status(
        "Explain why bank verification is unavailable before escalating.",
        true,
      );
      return;
    }
    const cid = snapshot.case_id;
    await api("/v1/cases/" + cid + "/bank-verification/unavailable", {
      method: "POST",
      body: JSON.stringify({ expected_revision: snapshot.revision, reason }),
    });
    await loadCase(cid, false, epoch);
    if (epoch !== routeEpoch) return;
    status(
      "Bank-side limitation recorded. A reviewer can assess escalation with the gaps retained.",
    );
  });
$("approve").onclick = () => {
  const reason = $("reason").value.trim();
  if (!reason) {
    status("Enter a review reason describing what you checked.", true);
    $("reason").focus();
    return;
  }
  const s = snapshot,
    disposition =
      s.readiness.disposition === "COMPLETE_CANDIDATE"
        ? "COMPLETE_HANDOFF"
        : "ESCALATE_WITH_GAPS";
  openConfirmation(
    disposition === "COMPLETE_HANDOFF"
      ? "Approve this case?"
      : "Approve escalation with gaps?",
    "Your decision applies to revision " +
      s.revision +
      ". New evidence will require a new approval. No report is sent at this step.",
    "Confirm approval",
    async (epoch) => {
      const result = await api("/v1/cases/" + s.case_id + "/reviews", {
        method: "POST",
        body: JSON.stringify({
          expected_revision: s.revision,
          digest: s.digest,
          disposition,
          reason,
        }),
      });
      await loadCase(s.case_id, false, epoch);
      await refreshWorkspace();
      if (epoch !== routeEpoch) return;
      status(
        "Approval " +
          result.approval_id +
          " recorded for this revision. You can now send the simulated reports.",
      );
    },
  );
};
$("export").onclick = () => {
  const cid = snapshot.case_id;
  const retrieve = workflow.status === "completed";
  const deliver = async (epoch) => {
    const result = await api("/v1/cases/" + cid + "/exports", {
      method: "POST",
    });
    packetCache.set(cid, result.packet);
    await loadCase(cid, false, epoch);
    await refreshWorkspace();
    if (epoch !== routeEpoch) return;
    status(
      (retrieve
        ? "Retrieved the delivered packet. "
        : "Sent simulated reports. ") +
        result.outbound.length +
        " acknowledged deliveries. Packet " +
        result.packet.packet_id +
        ".",
    );
  };
  if (retrieve) perform($("export"), deliver);
  else
    openConfirmation(
      "Send to the local simulators?",
      "Send the approved CFCFRMS update and JSON case packet. No real bank or official reporting service is contacted.",
      "Send simulated reports",
      deliver,
    );
};
$("confirm-action").onclick = () => {
  const task = confirmTask;
  confirmTask = null;
  $("confirm-dialog").close();
  if (task) perform($("confirm-action"), task);
};
for (const button of document.querySelectorAll("[data-close]"))
  button.onclick = () => $(button.dataset.close).close();
for (const button of document.querySelectorAll("[data-tab]")) {
  button.onclick = () => showTab(button.dataset.tab);
  button.onkeydown = (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const all = [...document.querySelectorAll("[data-tab]")],
      index = all.indexOf(button);
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? all.length - 1
          : (index + (event.key === "ArrowRight" ? 1 : -1) + all.length) %
            all.length;
    showTab(all[next].dataset.tab);
    all[next].focus();
  };
}
$("diff").onclick = () => perform($("diff"), showDiff);
$("artifacts").onchange = () => {
  selectedEvidence = $("artifacts").value;
  highlighted = [];
  showEvidence(selectedEvidence);
};
$("role").onchange = () => {
  controls();
  if (snapshot) {
    renderRequests();
    renderNext();
    renderUrgent();
  }
};
$("refresh").onclick = () =>
  perform($("refresh"), async (epoch) => {
    const cid = !$("case-page").hidden ? snapshot?.case_id : null;
    await refreshWorkspace();
    if (epoch !== routeEpoch) return;
    if (cid) await loadCase(cid, false, epoch);
    if (epoch !== routeEpoch) return;
    status(
      "Workspace refreshed. " +
        (workflow && !$("case-page").hidden
          ? nextText(workflow)
          : "Choose a case to continue."),
    );
  });
window.addEventListener("hashchange", route);
document.querySelector(".skip-link").onclick = (event) => {
  event.preventDefault();
  $("main").focus();
};
setInterval(async () => {
  if (
    pending ||
    loading ||
    document.hidden ||
    $("create-dialog").open ||
    $("confirm-dialog").open
  )
    return;
  loading = true;
  try {
    if (!$("case-page").hidden && snapshot) {
      const cid = snapshot.case_id,
        epoch = routeEpoch;
      const current = await api("/v1/cases/" + cid + "/workflow");
      if (
        epoch === routeEpoch &&
        JSON.stringify(current) !== JSON.stringify(workflow)
      ) {
        // A live clock changes on every read; only rerender when workflow records actually change.
        if (
          current.revision !== workflow.revision ||
          current.status !== workflow.status ||
          current.approval?.approval_id !== workflow.approval?.approval_id ||
          current.job?.status !== workflow.job?.status
        ) {
          await loadCase(cid, false, epoch);
          if (epoch === routeEpoch)
            status("Case updated. " + nextText(workflow));
        }
      }
    } else await refreshWorkspace();
  } catch (error) {
    status(friendly(error), true);
  } finally {
    loading = false;
  }
}, 4000);
setInterval(() => {
  if (
    !snapshot?.clock ||
    snapshot.clock.replay ||
    !snapshot.clock.first_debit_at ||
    $("case-page").hidden
  )
    return;
  const times = snapshot.trail?.debit_clocks?.length
    ? snapshot.trail.debit_clocks.map((d) => d.ts)
    : [snapshot.clock.first_debit_at];
  const ages = times
    .map((t) => (Date.now() - Date.parse(t)) / 60000)
    .filter((m) => m >= 0);
  const deadlines = ages.filter((m) => m < 60).map((m) => 60 - m);
  $("clock-left").textContent = deadlines.length
    ? Math.min(...deadlines).toFixed(1) + " min remaining"
    : ages.length
      ? "Golden-hour windows elapsed"
      : "Debit time needs review";
  $("clock-note").textContent =
    "Live clock · " + times.length + " debit time(s) · next active deadline";
}, 1000);
fetch("/health")
  .then((r) => r.json())
  .then((h) => {
    $("runtime-note").textContent =
      "Current processing: " +
      h.provider +
      " / " +
      h.model +
      ". All reporting destinations are local simulators.";
  })
  .catch(() => {
    $("runtime-note").textContent =
      "Service status unavailable. Refresh after the local services are running.";
  });
route();
function showEvidence(id, highlight = []) {
  if (!id) return;
  const a = snapshot.artifacts.find((a) => a.artifact_id === id),
    segments = snapshot.segments.filter((s) => s.artifact_id === id);
  $("artifacts").value = id;
  clear("boxes");
  $("source-note").textContent =
    a.mime_type +
    " / sha256 " +
    a.sha256.slice(0, 12) +
    " / " +
    (segments.some((s) => s.source === "model_ocr")
      ? "Model OCR: " +
        segments.find((s) => s.source === "model_ocr").ocr_model_id
      : "Exact text or awaiting OCR");
  $("segment-text").textContent = segments
    .filter((s) => highlight.includes(s.segment_id))
    .map((s) => s.text)
    .join("\n");
  if (a.mime_type.startsWith("image/")) {
    $("canvas").style.display = "block";
    $("evidence-text").hidden = true;
    $("evidence-image").src =
      "/v1/cases/" +
      encodeURIComponent(snapshot.case_id) +
      "/artifacts/" +
      encodeURIComponent(id) +
      "/content";
    for (const s of segments) {
      if (!s.box_2d) continue;
      const [y, x, Y, X] = s.box_2d,
        box = element(
          "div",
          undefined,
          "box" + (highlight.includes(s.segment_id) ? " selected" : ""),
        );
      Object.assign(box.style, {
        top: y / 10 + "%",
        left: x / 10 + "%",
        width: (X - x) / 10 + "%",
        height: (Y - y) / 10 + "%",
      });
      box.setAttribute("role", "button");
      box.tabIndex = 0;
      box.setAttribute("aria-label", s.text);
      box.onclick = () => showEvidence(id, [s.segment_id]);
      box.onkeydown = (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          showEvidence(id, [s.segment_id]);
        }
      };
      $("boxes").append(box);
    }
  } else {
    $("canvas").style.display = "none";
    $("evidence-text").hidden = false;
    $("evidence-text").textContent = segments.map((s) => s.text).join("\n");
  }
}
function svg(tag, attrs = {}, text) {
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text !== undefined) n.textContent = text;
  return n;
}
function drawTrail() {
  const canvas = $("trail-svg");
  canvas.replaceChildren();
  const transfers = snapshot.trail?.transfers || [];
  if (!transfers.length) return;
  const nodes = new Set(),
    edges = [];
  for (const t of transfers) {
    nodes.add(t.from_account);
    nodes.add(t.to_account);
    const amount = (snapshot.trail.positions || [])
      .filter((p) => p.path.includes(t.txn_id))
      .reduce((sum, p) => sum + p.amount_minor, 0);
    if (amount) edges.push({ ...t, ownAmount: amount });
  }
  const root = [...nodes].find((n) => !edges.some((t) => t.to_account === n)),
    depth = new Map([[root, 0]]);
  for (let i = 0; i < nodes.size; i++)
    for (const t of edges)
      if (depth.has(t.from_account) && !depth.has(t.to_account))
        depth.set(t.to_account, depth.get(t.from_account) + 1);
  const buckets = new Map();
  for (const n of nodes) {
    const d = depth.get(n) || 0;
    if (!buckets.has(d)) buckets.set(d, []);
    buckets.get(d).push(n);
  }
  const xy = new Map();
  for (const [d, list] of buckets)
    list.sort().forEach((n, i) => xy.set(n, [12 + d * 205, 35 + i * 145]));
  const coordinates = [...xy.values()];
  canvas.setAttribute(
    "viewBox",
    "0 0 " +
      Math.max(600, ...coordinates.map(([x]) => x + 170)) +
      " " +
      Math.max(250, ...coordinates.map(([, y]) => y + 90)),
  );
  const defs = svg("defs"),
    marker = svg("marker", {
      id: "arrow",
      viewBox: "0 0 10 10",
      refX: 9,
      refY: 5,
      markerWidth: 6,
      markerHeight: 6,
      orient: "auto-start-reverse",
    });
  marker.append(svg("path", { d: "M 0 0 L 10 5 L 0 10 Z", fill: "#4988a0" }));
  defs.append(marker);
  canvas.append(defs);
  for (const t of edges) {
    const [x, y] = xy.get(t.from_account),
      [X, Y] = xy.get(t.to_account);
    canvas.append(
      svg("path", {
        d: `M ${x + 150} ${y + 30} C ${x + 178} ${y + 30},${X - 28} ${Y + 30},${X} ${Y + 30}`,
        fill: "none",
        stroke: "#4988a0",
        "stroke-width": 2,
        "marker-end": "url(#arrow)",
      }),
    );
    const label = svg(
      "text",
      {
        x: (x + 150 + X) / 2,
        y: (y + Y) / 2 + 17,
        "font-size": 12,
        "text-anchor": "middle",
        fill: "#16394f",
      },
      money(t.ownAmount),
    );
    label.append(svg("title", {}, t.txn_id + " / " + t.ts + " / " + t.source));
    canvas.append(
      label,
      svg(
        "text",
        {
          x: (x + 150 + X) / 2,
          y: (y + Y) / 2 + 33,
          "font-size": 9,
          "text-anchor": "middle",
          fill: "#597083",
        },
        t.ts.slice(11, 16),
      ),
    );
  }
  for (const [n, [x, y]] of xy) {
    const account = snapshot.trail.accounts?.find((a) => a.id === n);
    canvas.append(
      svg("rect", {
        x,
        y,
        width: 150,
        height: 60,
        rx: 6,
        fill: account?.kind === "cashout" ? "#fff0d7" : "#e9f2f6",
        stroke: "#b3cad8",
      }),
      svg(
        "text",
        {
          x: x + 75,
          y: y + 25,
          "text-anchor": "middle",
          "font-size": 13,
          fill: "#16394f",
        },
        n === root ? "Victim debits" : n,
      ),
      svg(
        "text",
        {
          x: x + 75,
          y: y + 44,
          "text-anchor": "middle",
          "font-size": 10,
          fill: "#597083",
        },
        account?.bank || "Synthetic bank",
      ),
    );
  }
}

function renderBrief() {
  const b = workflow.brief;
  if (!b) return;
  $("brief-summary").textContent = b.summary;
  const modes = [
    ...new Set(
      b.providers.map((r) => r.provider + " / " + r.model_id + " / " + r.mode),
    ),
  ];
  $("provider-mode").textContent = modes.length
    ? "Actual processing: " + modes.join("; ")
    : "Evidence not yet processed. No AI result is claimed.";
  $("brief-download").href = "/v1/cases/" + snapshot.case_id + "/brief";
  const parent = $("brief-content");
  parent.replaceChildren();
  const section = (title, rows) => {
    const d = element("details");
    d.append(element("summary", title));
    for (const row of rows) d.append(element("p", row));
    parent.append(d);
  };
  parent.append(
    element(
      "p",
      "Next action: " +
        b.recommended_action.action +
        " · Owner: " +
        b.recommended_action.owner,
    ),
  );
  parent.append(element("p", b.recommended_action.reason));
  section(
    "Payment inventory",
    b.payments.map(
      (p) =>
        p.txn_id +
        " · " +
        money(p.amount_minor) +
        " · " +
        p.status +
        " · " +
        p.source_category +
        " · " +
        p.source_id,
    ),
  );
  const d = element("details");
  d.append(element("summary", "Victim statements and source citations"));
  for (const c of b.victim_statements) {
    d.append(
      element(
        "p",
        (factNames[c.kind] || c.kind) + ": " + c.value + " · " + c.state,
      ),
    );
    for (const src of c.sources) {
      const chip = element("button", src.segment_id, "source-chip");
      chip.onclick = () => {
        showTab("evidence");
        selectedEvidence = src.artifact_id;
        highlighted = [src.segment_id];
        showEvidence(selectedEvidence, highlighted);
      };
      d.append(chip);
    }
  }
  parent.append(d);
  section(
    "Chronology and provenance",
    b.chronology.map(
      (t) =>
        (t.at || "Time unknown") +
        " · " +
        t.event +
        " · " +
        t.source_category +
        " · " +
        t.source_id,
    ),
  );
  section(
    "Conflicts and unknowns",
    b.conflicts
      .map(
        (c) =>
          c.kind +
          ": " +
          c.value +
          " · " +
          c.sources.map((s) => s.segment_id).join(", "),
      )
      .concat(b.unknowns.map((k) => factNames[k] || k)),
  );
  section(
    "Downstream bank observations",
    b.downstream_observations.map(
      (r) =>
        r.bank +
        " · " +
        r.account +
        " · " +
        money(r.balance_minor) +
        " · observed " +
        r.reported_at +
        " · " +
        r.update_id,
    ),
  );
  parent.append(
    element(
      "p",
      b.approval
        ? "Approval rationale: " +
            b.approval.reason +
            " · " +
            b.approval.reviewer.user_id +
            " · revision " +
            b.approval.revision
        : "Human approval not yet recorded for this revision.",
    ),
  );
  parent.append(element("p", b.limitations, "muted"));
}

function renderFollowup() {
  const f = workflow.followup;
  $("followup-state").textContent =
    "Owner: " + f.owner + " · " + f.state + " · " + f.next_action;
  if (!$("followup-panel").contains(document.activeElement)) {
    $("followup-owner").value = f.owner;
    $("followup-action").value = f.next_action;
    if (f.due_at) {
      const d = new Date(f.due_at);
      $("followup-due").value = new Date(
        d.getTime() - d.getTimezoneOffset() * 60000,
      )
        .toISOString()
        .slice(0, 16);
    } else $("followup-due").value = "";
  }
}
$("followup-save").onclick = () =>
  perform($("followup-save"), async (epoch) => {
    const cid = snapshot.case_id;
    await api("/v1/cases/" + cid + "/followup", {
      method: "POST",
      body: JSON.stringify({
        expected_revision: snapshot.revision,
        expected_version: workflow.followup.version,
        owner: $("followup-owner").value,
        next_action: $("followup-action").value,
        state: workflow.historical_deliveries.length
          ? "awaiting_external"
          : "open",
        reason: $("followup-reason").value,
        due_at: $("followup-due").value
          ? new Date($("followup-due").value).toISOString()
          : null,
      }),
    });
    await loadCase(cid, false, epoch);
    status("Follow-up recorded. Financial approval scope is unchanged.");
  });
