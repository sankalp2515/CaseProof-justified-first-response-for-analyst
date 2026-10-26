import { it, expect } from "vitest";
import { createAuth } from "../../src/api/auth.js";
import { queueChanges } from "../../src/models/queue.js";
it("never sends a demo role in cloud mode and expires volatile tokens", () => {
  let now = 1000;
  const auth = createAuth("cloud", () => now);
  expect(() => auth.headers("reviewer")).toThrow("Sign in");
  auth.accept("temporary-id-token", 2000);
  expect(auth.headers("reviewer")).toEqual({
    Authorization: "Bearer temporary-id-token",
  });
  expect(auth.headers()).toEqual({});
  now = 2001;
  expect(() => auth.headers("analyst")).toThrow("Sign in");
});
it("demo mode uses only supported identities", () => {
  const auth = createAuth("local");
  expect(auth.headers("admin")).toEqual({ "X-Demo-User": "admin" });
  expect(() => auth.headers("invented")).toThrow();
});
it("cloud practice access uses labelled personas without a token", () => {
  const auth = createAuth("cloud", () => 0, "practice");
  expect(auth.ready()).toBe(true);
  expect(auth.access).toBe("practice");
  expect(auth.headers("analyst")).toEqual({ "X-Demo-User": "analyst" });
  expect(() => auth.headers("invented")).toThrow();
});
it("only announces real arrivals after baseline, then workflow changes", () => {
  expect(queueChanges(null, [{ case_id: "A", status: "new" }])).toEqual([]);
  expect(
    queueChanges(
      [{ case_id: "A", status: "new" }],
      [
        { case_id: "A", status: "processing" },
        { case_id: "B", status: "new" },
      ],
    ).map((x) => x.type),
  ).toEqual(["updated", "arrived"]);
});
