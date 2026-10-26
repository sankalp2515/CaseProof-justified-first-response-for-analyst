import { it, expect } from "vitest";
import { tourOutcome } from "../../src/models/tourOutcome.js";
const deliveries = [
  { kind: "case_ticket", status: "sent" },
  { kind: "cfcfrms_report_update", status: "sent" },
];
it("does not treat historical acknowledgements as delivery of a reassessed revision", () => {
  expect(
    tourOutcome({
      status: "needs_attention",
      historical_deliveries: deliveries,
      deliveries: [],
    }).delivered,
  ).toBe(false);
});
it("requires an explicitly saved owner and next action, not version-zero defaults", () => {
  const followup = {
    version: 0,
    owner: "fraud_analyst",
    next_action: "Track bank response",
    state: "awaiting_external",
  };
  expect(
    tourOutcome({ status: "completed", deliveries, followup }).complete,
  ).toBe(false);
  expect(
    tourOutcome({
      status: "completed",
      deliveries,
      followup: { ...followup, version: 1 },
    }).complete,
  ).toBe(true);
});
