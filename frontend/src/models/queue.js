export function queueChanges(previous, current) {
  if (!previous) return [];
  const known = new Map(previous.map((row) => [row.case_id, row]));
  return current.flatMap((row) => {
    const old = known.get(row.case_id);
    return !old
      ? [{ ...row, type: "arrived" }]
      : old.status !== row.status
        ? [{ ...row, type: "updated" }]
        : [];
  });
}

// A visitor switching from reporting to staff did not have the queue open at
// arrival. Surface current server priority without pretending it arrived now.
export function initialPriorityAlerts(rows) {
  return rows
    .filter(
      (row) =>
        row.clock?.golden_hour_remaining > 0 &&
        !["completed", "approved"].includes(row.status) &&
        row.followup?.state !== "awaiting_external",
    )
    .map((row) => ({ ...row, type: "priority" }));
}

export function refreshAlertRows(alerts, rows) {
  const latest = new Map(rows.map((row) => [row.case_id, row]));
  return alerts.map((alert) => ({
    ...alert,
    ...latest.get(alert.case_id),
    eventId: alert.eventId,
    type: alert.type,
    seen: alert.seen,
  }));
}

// Identity switches and background reassessments are not new complaints.
// Store only identifiers/read state; current facts always come from the server.
export function notificationLedger(previous, rows) {
  const ledger = previous || { initialized: false, known: [], events: [] };
  const known = new Set(ledger.known);
  const initial = new Set(
    initialPriorityAlerts(rows).map((row) => row.case_id),
  );
  const events = [...ledger.events];
  for (const row of rows) {
    if (
      !known.has(row.case_id) &&
      (ledger.initialized || initial.has(row.case_id))
    ) {
      events.unshift({
        case_id: row.case_id,
        eventId: row.case_id + ":arrival",
        type: ledger.initialized ? "arrived" : "priority",
        seen: false,
      });
    }
    known.add(row.case_id);
  }
  return { initialized: true, known: [...known], events: events.slice(0, 100) };
}

export function visibleNotifications(ledger, rows) {
  const current = new Map(rows.map((row) => [row.case_id, row]));
  return ledger.events
    .filter((event) => current.has(event.case_id))
    .map((event) => ({ ...current.get(event.case_id), ...event }));
}
