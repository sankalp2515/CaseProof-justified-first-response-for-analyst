import React from "react";
import { render, screen, cleanup } from "@testing-library/react";
import { it, expect, afterEach, vi } from "vitest";
vi.mock("../../src/state/resources.jsx", () => ({
  useSession: () => ({ persona: "analyst" }),
}));
import Queue from "../../src/pages/LiveQueue.jsx";
afterEach(cleanup);
const resource = {
  data: { cases: [], counts: { total: 0 } },
  reload: () => {},
  updated: null,
};
it("shows a history register rather than command-center KPIs for Cases", () => {
  render(<Queue mode="cases" activeResource={resource} />);
  expect(screen.getByRole("heading", { name: "Case register" })).toBeTruthy();
  expect(
    screen.getByRole("columnheader", { name: "Delivery history" }),
  ).toBeTruthy();
  expect(screen.queryByText("Golden-hour priority")).toBeNull();
});
it("keeps response-priority triage in Queue", () => {
  render(
    <Queue
      mode="queue"
      activeResource={resource}
      scope="active"
      setScope={() => {}}
    />,
  );
  expect(screen.getByText("Golden-hour priority")).toBeTruthy();
  expect(
    screen.queryByRole("columnheader", { name: "Delivery history" }),
  ).toBeNull();
});
