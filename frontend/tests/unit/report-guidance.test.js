import { it, expect } from "vitest";
import {
  recentPayments,
  contactWarning,
} from "../../src/models/reportGuidance.js";
it("sorts payments by actual time, with deterministic ties, without mutating bank data", () => {
  const rows = [
    { txn_id: "old", ts: "2026-10-14T10:00:00Z" },
    { txn_id: "new", ts: "2026-10-17T10:00:00Z" },
  ];
  expect(recentPayments(rows).map((x) => x.txn_id)).toEqual(["new", "old"]);
  expect(rows[0].txn_id).toBe("old");
});
it("explains contact after a selected payment without moving the bank clock", () => {
  const rows = [{ txn_id: "t", ts: "2026-10-17T21:53:00+05:30" }];
  expect(contactWarning("2026-10-17T22:28:00+05:30", ["t"], rows)).toMatch(
    /after a selected payment/,
  );
  expect(contactWarning("2026-10-17T21:40:00+05:30", ["t"], rows)).toBe("");
  expect(contactWarning("", ["t"], rows)).toBe("");
});
