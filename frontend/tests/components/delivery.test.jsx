import React from "react";
import { it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
vi.mock("../../src/state/resources.jsx", async (original) => ({
  ...(await original()),
  useSession: () => ({ persona: "analyst" }),
  useResource: () => ({ data: [], reload: vi.fn() }),
}));
import Delivery from "../../src/pages/case/LiveDelivery.jsx";
afterEach(cleanup);
it("preserves delivered destination status when newer evidence invalidates approval", () => {
  const view = {
    snapshot: { case_id: "CASE-A", revision: 18 },
    workflow: {
      status: "ready_for_review",
      historical_deliveries: [
        {
          kind: "case_ticket",
          revision: 16,
          packet_id: "PACKET-A",
          response: { received: true },
        },
      ],
      followup: { history: [] },
    },
  };
  render(<Delivery view={view} reload={() => {}} />);
  expect(
    screen.getByText(
      "Delivered revision 16; current revision 18 needs its own review",
    ),
  ).toBeTruthy();
  expect(screen.getByText("No urgent referrals recorded.")).toBeTruthy();
});
