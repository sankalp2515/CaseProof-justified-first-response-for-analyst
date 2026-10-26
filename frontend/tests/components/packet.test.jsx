import React from "react";
import { it, expect, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, act } from "@testing-library/react";
import PacketDocument from "../../src/pages/case/PacketDocument.jsx";
import packet from "./packet.fixture.json";
afterEach(cleanup);

it("renders the delivered packet as a readable two-part report", async () => {
  await act(async () => { render(<PacketDocument packet={packet} />); });
  expect(screen.getByText("Payment scam investigation report")).toBeTruthy();
  expect(screen.getByText(/1 · Bank case ticket/)).toBeTruthy();
  expect(screen.getByText(/2 · Cybercrime report update/)).toBeTruthy();
  expect(screen.getByText("escalate with gaps")).toBeTruthy();
  expect(screen.getByText("Where the money was traced")).toBeTruthy();
  expect(screen.getAllByText(/₹56,000/).length).toBeGreaterThan(0);
  expect(screen.queryByText(/"packet_id"/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /Show raw data/ }));
  expect(screen.getByText(/"packet_id"/)).toBeTruthy();
});
