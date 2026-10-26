export function recentPayments(rows) {
  return [...rows].sort(
    (a, b) =>
      Date.parse(b.ts) - Date.parse(a.ts) || a.txn_id.localeCompare(b.txn_id),
  );
}
export function contactWarning(first, selected, rows) {
  if (!first) return "";
  const stamp = Date.parse(first);
  if (!Number.isFinite(stamp))
    return "Enter a valid contact time, or leave it blank.";
  if (rows.some((t) => selected.includes(t.txn_id) && stamp > Date.parse(t.ts)))
    return "This contact time is after a selected payment. Check whether you meant the reporting time. Correct it, leave it blank if unknown, or confirm it is accurate. The response window still starts from the bank payment time.";
  return "";
}
