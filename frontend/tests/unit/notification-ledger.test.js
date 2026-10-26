import { it, expect } from "vitest";
import {
  notificationLedger,
  visibleNotifications,
} from "../../src/models/queue.js";
const row = (status = "processing", id = "A") => ({
  case_id: id,
  status,
  clock: { golden_hour_remaining: 1800 },
});
it("does not reannounce after role changes, repeated polling or processing transitions", () => {
  let ledger = notificationLedger(null, [row()]);
  ledger.events[0].seen = true;
  for (const status of ["ready_for_review", "processing", "ready_for_review"])
    ledger = notificationLedger(JSON.parse(JSON.stringify(ledger)), [
      row(status),
    ]);
  expect(ledger.events).toHaveLength(1);
  expect(visibleNotifications(ledger, [row()])[0].seen).toBe(true);
});
it("announces a real arrival once and keeps other practice sessions out of view", () => {
  let ledger = notificationLedger(null, []);
  ledger = notificationLedger(ledger, [row()]);
  expect(ledger.events[0].type).toBe("arrived");
  ledger = notificationLedger(ledger, [row("processing", "B")]);
  expect(
    visibleNotifications(ledger, [row("processing", "B")]).map(
      (x) => x.case_id,
    ),
  ).toEqual(["B"]);
  expect(notificationLedger(ledger, [row()]).events).toHaveLength(2);
});
