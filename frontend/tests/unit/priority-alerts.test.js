import { it, expect } from "vitest";
import {
  initialPriorityAlerts,
  refreshAlertRows,
} from "../../src/models/queue.js";

it("surfaces server priority when switching from victim without inventing arrival", () => {
  const rows = [
    {
      case_id: "A",
      status: "ready_for_review",
      clock: { golden_hour_remaining: 25 },
    },
    {
      case_id: "B",
      status: "needs_attention",
      clock: { golden_hour_remaining: 0 },
    },
    { case_id: "C", status: "completed", clock: { golden_hour_remaining: 25 } },
    {
      case_id: "D",
      status: "processing",
      clock: { golden_hour_remaining: null },
    },
  ];
  expect(initialPriorityAlerts(rows).map((x) => [x.case_id, x.type])).toEqual([
    ["A", "priority"],
  ]);
});

it("refreshes alert facts and elapsed windows without recreating the arrival event", () => {
  const old = {
    case_id: "A",
    eventId: "first",
    type: "arrived",
    seen: false,
    clock: { golden_hour_remaining: 5 },
  };
  const refreshed = refreshAlertRows(
    [old],
    [
      {
        case_id: "A",
        victim_summary: "Assessed account",
        clock: { golden_hour_remaining: 0 },
      },
    ],
  )[0];
  expect(refreshed.clock.golden_hour_remaining).toBe(0);
  expect(refreshed.victim_summary).toBe("Assessed account");
  expect(refreshed.eventId).toBe("first");
  expect(refreshed.type).toBe("arrived");
  expect(refreshed.seen).toBe(false);
  expect(old.clock.golden_hour_remaining).toBe(5);
});
