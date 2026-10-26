import React from "react";
import { it, expect, vi, afterEach } from "vitest";
import {
  renderHook,
  act,
  render,
  screen,
  fireEvent,
  cleanup,
} from "@testing-library/react";
import { useResource } from "../../src/state/resources.jsx";
import { Modal } from "../../src/components/live.jsx";
import { boxStyle } from "../../src/pages/case/LiveEvidence.jsx";
import { makeTrailView, layoutTrail } from "../../src/pages/case/LiveTrail.jsx";
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
it("ignores an old case response after navigating to a different case", async () => {
  let resolveA;
  const pending = new Promise((r) => (resolveA = r));
  const { result, rerender } = renderHook(
    ({ id }) =>
      useResource(
        id,
        () => (id === "A" ? pending : Promise.resolve({ id: "B" })),
        60000,
      ),
    { initialProps: { id: "A" } },
  );
  rerender({ id: "B" });
  await act(async () => {});
  expect(result.current.data).toEqual({ id: "B" });
  await act(async () => resolveA({ id: "A" }));
  expect(result.current.data).toEqual({ id: "B" });
});
it("clears protected data when a current session is denied", async () => {
  vi.useFakeTimers();
  let denied = false;
  const load = vi.fn(() =>
    denied
      ? Promise.reject(Object.assign(new Error("Denied"), { status: 403 }))
      : Promise.resolve({ protected: true }),
  );
  const { result } = renderHook(() => useResource("case", load, 1000));
  await act(async () => {});
  expect(result.current.data.protected).toBe(true);
  denied = true;
  await act(async () => vi.advanceTimersByTimeAsync(1000));
  expect(result.current.data).toBe(null);
});
it("focuses dialogs, traps tab and restores the trigger focus", () => {
  const close = vi.fn();
  const trigger = document.createElement("button");
  trigger.textContent = "Open";
  document.body.append(trigger);
  trigger.focus();
  const { unmount } = render(
    <Modal title="Decision" onClose={close} footer={<button>Confirm</button>}>
      <input aria-label="Reason" />
    </Modal>,
  );
  expect(screen.getByRole("button", { name: "Close" })).toBe(
    document.activeElement,
  );
  screen.getByRole("button", { name: "Confirm" }).focus();
  fireEvent.keyDown(document, { key: "Tab" });
  expect(document.activeElement).toBe(
    screen.getByRole("button", { name: "Close" }),
  );
  fireEvent.keyDown(document, { key: "Escape" });
  expect(close).toHaveBeenCalledTimes(1);
  unmount();
  expect(document.activeElement).toBe(trigger);
  trigger.remove();
});
it("maps source coordinates in top-left-bottom-right order", () => {
  expect(boxStyle([100, 200, 300, 600])).toEqual({
    top: "10%",
    left: "20%",
    width: "40%",
    height: "20%",
  });
});
it("layouts arbitrary cyclic transfers without inventing available funds", () => {
  const s = {
    clock: { as_of: "2026-10-16T10:00:00Z" },
    trail: {
      accounts: [
        { id: "A", bank: "Cedar", label: "A", opening_balance: 999999 },
      ],
      transfers: [
        {
          txn_id: "1",
          from_account: "A",
          to_account: "B",
          amount_minor: 100,
          ts: "2026-10-16T09:00:00Z",
        },
        {
          txn_id: "2",
          from_account: "B",
          to_account: "A",
          amount_minor: 50,
          ts: "2026-10-16T09:01:00Z",
        },
      ],
      positions: [{ account: "B", amount_minor: 50, status: "unaccounted" }],
      summary: { recoverable: 0, unaccounted: 50, left_system: 0 },
    },
  };
  const trail = makeTrailView(s),
    graph = layoutTrail(trail);
  expect(graph.nodes).toHaveLength(2);
  expect(graph.edges).toHaveLength(2);
  expect(trail.summary.recoverable).toBe(0);
  expect(
    graph.nodes.every((n) => Number.isFinite(n.x) && Number.isFinite(n.y)),
  ).toBe(true);
});
