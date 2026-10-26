import { describe, it, expect, vi } from "vitest";
import {
  validateFiles,
  reconcileUploads,
} from "../../src/features/victim/submission.js";
const limits = {
  max_file_bytes: 5 * 1024 * 1024,
  max_case_bytes: 20 * 1024 * 1024,
  max_artifacts: 6,
  mime_types: ["image/png", "image/jpeg", "text/plain"],
};
describe("evidence budgeting and recovery", () => {
  it("reserves narrative slot and bytes", () => {
    expect(
      validateFiles(
        Array.from({ length: 6 }, () => ({ size: 100, type: "text/plain" })),
        "a narrative",
        limits,
      ),
    ).toMatch(/5/);
    expect(
      validateFiles(
        [{ size: 6 * 1024 * 1024, type: "image/png" }],
        "story",
        limits,
      ),
    ).toMatch(/5 MiB/);
    expect(
      validateFiles([{ size: 100, type: "application/pdf" }], "story", limits),
    ).toMatch(/PNG/);
    expect(
      validateFiles([{ size: 100, type: "image/png" }], "story", limits),
    ).toBe(null);
  });
  it("does not retry an acknowledged file after a lost response", () => {
    expect(
      reconcileUploads(
        [
          { sha256: "abc", name: "proof.png" },
          { sha256: "def", name: "other.png" },
        ],
        [{ sha256: "abc" }],
      ),
    ).toEqual([
      { sha256: "abc", name: "proof.png", state: "received" },
      { sha256: "def", name: "other.png", state: "pending" },
    ]);
  });
});
