import { describe, it, expect, vi } from "vitest";
import {
  formatMinor,
  remaining,
  makeCaseView,
} from "../../src/models/caseView.js";
import { apiRequest, loadCaseView } from "../../src/api/client.js";

describe("money and coherent financial views", () => {
  it("keeps exact paise and treats unknown separately from zero", () => {
    expect(formatMinor(4827401)).toBe("₹48,274.01");
    expect(formatMinor(0)).toBe("₹0.00");
    expect(formatMinor(null)).toBe("—");
    expect(() => formatMinor(Number.MAX_SAFE_INTEGER + 1)).toThrow();
    expect(remaining(1.5)).toBe("01:30");
    expect(remaining(null)).toBe("Unknown");
  });
  it("rejects mismatched snapshot and workflow", () => {
    expect(() =>
      makeCaseView(
        { case_id: "A", revision: 1, digest: "a" },
        { case_id: "A", revision: 2, digest: "b" },
      ),
    ).toThrow("Updating assessment");
  });
  it("keeps candidate totals out of confirmed loss", () => {
    const v = makeCaseView(
      { case_id: "A", revision: 1, digest: "a" },
      {
        case_id: "A",
        revision: 1,
        digest: "a",
        confirmed_disputed_minor: 50000,
        additional_candidate_minor: 10000,
      },
    );
    expect(v.amounts.confirmed).toBe(50000);
    expect(v.amounts.candidate).toBe(10000);
  });
});
describe("API transport", () => {
  it.each([403, 404, 409, 422, 429, 503])(
    "normalises %s without retrying mutations",
    async (status) => {
      const fetcher = vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ error: "conflict" }), { status }),
        );
      await expect(
        apiRequest("/v1/x", { method: "POST", body: {}, fetcher }),
      ).rejects.toMatchObject({ status, code: "conflict" });
      expect(fetcher).toHaveBeenCalledTimes(1);
    },
  );
  it("waits while a practice bank is still being prepared, then reads", async () => {
    vi.useFakeTimers();
    const preparing = () =>
      new Response(JSON.stringify({ detail: "bank_data_preparing" }), {
        status: 503,
        headers: { "Retry-After": "1" },
      });
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(preparing())
      .mockResolvedValueOnce(preparing())
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true })));
    const result = apiRequest("/v1/victim/me", { fetcher });
    await vi.advanceTimersByTimeAsync(2500);
    await expect(result).resolves.toEqual({ ok: true });
    expect(fetcher).toHaveBeenCalledTimes(3);
    vi.useRealTimers();
  });
  it("does not wait on other server errors", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "scanner_unavailable" }), {
        status: 503,
      }),
    );
    await expect(apiRequest("/v1/x", { fetcher })).rejects.toMatchObject({
      status: 503,
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("maps schema errors to fields", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: [{ loc: ["body", "narrative"], msg: "Too short" }],
        }),
        { status: 422 },
      ),
    );
    await expect(apiRequest("/v1/x", { fetcher })).rejects.toMatchObject({
      fieldErrors: { narrative: "Too short" },
    });
  });
  it("only publishes matching revision/digest and limits reconciliation", async () => {
    const fetcher = vi.fn().mockImplementation(
      async (url) =>
        new Response(
          JSON.stringify({
            case_id: "A",
            revision: url.endsWith("workflow") ? 2 : 1,
            digest: "x",
          }),
        ),
    );
    await expect(loadCaseView("A", { fetcher })).rejects.toThrow(
      "Updating assessment",
    );
    expect(fetcher).toHaveBeenCalledTimes(6);
  });
});
