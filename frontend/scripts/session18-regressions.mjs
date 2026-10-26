import { chromium } from "playwright";
import fs from "node:fs/promises";
import assert from "node:assert/strict";
import {fileURLToPath} from "node:url";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const base = "http://caseproof-journey.localhost:8188";
const out = new URL("../../var/session-18/", import.meta.url);
await fs.mkdir(out, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 574, height: 668 },
  reducedMotion: "reduce",
});
const page = await context.newPage();
const checks = [],
  audits = [],
  errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const check = (name, value) => {
  assert.ok(value, name);
  checks.push(name);
  console.log("PASS", name);
};
const shot = (name) =>
  page.screenshot({
    path: fileURLToPath(new URL(name + ".png", out)),
  });
const cid = "CASE-0999285a134ff919";
const read = (path) =>
  page.evaluate(async (path) => {
    const r = await fetch(path, {
      headers: { "X-Demo-User": "analyst" },
      credentials: "include",
    });
    if (!r.ok) throw Error("API " + r.status);
    return r.json();
  }, path);
async function axe(name) {
  await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
  const violations = await page.evaluate(async () =>
    (
      await axe.run(document, {
        runOnly: {
          type: "tag",
          values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"],
        },
      })
    ).violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      nodes: v.nodes.length,
    })),
  );
  audits.push({ screen: name, violations });
  check(name + " automated accessibility", violations.length === 0);
}
try {
  await page.goto(base + "/app/#/staff/cases/" + cid + "/overview");
  await page
    .getByRole("heading", { name: "Payment inventory", exact: true })
    .waitFor();
  const dimensions = await page.evaluate(() => {
    const box = (s) =>
      document.querySelector(s).getBoundingClientRect().toJSON();
    return {
      summary: box(".case-summary"),
      stats: box(".case-h .stats"),
      avatar: box(".staff-identity .avatar"),
      select: box(".persona-label select"),
      top: box(".top"),
      width: innerWidth,
      scroll: document.documentElement.scrollWidth,
    };
  });
  check("574px case summary uses full width", dimensions.summary.width > 500);
  check(
    "574px stats occupy their own row",
    dimensions.stats.top >= dimensions.summary.bottom,
  );
  check(
    "574px identity avatar is visible and aligned to selected role",
    dimensions.avatar.width === 30 &&
      Math.abs(dimensions.avatar.bottom - dimensions.select.bottom) < 2,
  );
  check(
    "574px page has no body overflow",
    dimensions.scroll <= dimensions.width,
  );
  await shot("after-mobile-header");
  await axe("mobile-overview");
  await page.setViewportSize({ width: 1242, height: 668 });
  await page.getByRole("button", { name: "Requests", exact: true }).click();
  await page.locator(".request-explanation").waitFor();
  const spacing = await page
    .locator(".request-explanation")
    .evaluate((e) => ({
      gap: parseFloat(getComputedStyle(e).gap),
      padding: parseFloat(getComputedStyle(e).paddingTop),
    }));
  check(
    "Requests explanation has explicit padding and vertical spacing",
    spacing.gap >= 14 && spacing.padding >= 18,
  );
  await shot("after-requests");
  await axe("requests");
  await page
    .getByRole("button", { name: "Review & decision", exact: true })
    .click();
  await page.getByText("When would I use this?", { exact: true }).click();
  await shot("urgent-referral-explanation");
  await page.goto(base + "/app/#/staff/queue");
  await page.getByRole("button", { name: /Notifications, / }).waitFor();
  await page.getByRole("button", { name: /Notifications, / }).click();
  await page.getByRole("button", { name: "Mark read", exact: true }).click();
  await page.getByRole("button", { name: /Notifications, / }).click();
  for (const role of ["reviewer", "analyst", "reviewer", "analyst"]) {
    await page
      .getByRole("combobox", { name: "Staff persona", exact: true })
      .selectOption(role);
    await page.waitForTimeout(800);
  }
  check(
    "Role switching does not recreate unread alerts",
    (await page
      .getByRole("button", { name: /Notifications, / })
      .getAttribute("aria-label")) === "Notifications, 0 unread",
  );
  check(
    "Role switching does not reopen golden-hour popup",
    (await page
      .getByRole("status", { name: "Golden-hour priority alert", exact: true })
      .count()) === 0,
  );
  await page.getByRole("button", { name: "Cases", exact: true }).click();
  await page.waitForTimeout(1200);
  await page.getByRole("button", { name: "Queue", exact: true }).click();
  await page.waitForTimeout(1200);
  await page.reload();
  await page
    .getByRole("button", { name: "Notifications, 0 unread", exact: true })
    .waitFor();
  check("Read state survives Cases/Queue scope changes and reload", true);
  await page.goto(base + "/");
  check(
    "Landing favicon resolves to actual SVG",
    await page.evaluate(async () => {
      const r = await fetch("/app/favicon.svg");
      return r.ok && r.headers.get("content-type").includes("image/svg+xml");
    }),
  );
  await page.getByRole("link", { name: /Take the guided tour/ }).click();
  await page
    .getByRole("heading", { name: "Welcome: the golden hour", exact: true })
    .waitFor();
  check("Landing tour opens at introduction", true);
  await page.getByRole("button", { name: /Next/ }).click();
  await page.getByRole("button", { name: "Close tour", exact: true }).click();
  await page.getByRole("button", { name: "Tour", exact: true }).click();
  await page
    .getByRole("heading", { name: "Welcome: the golden hour", exact: true })
    .waitFor();
  check("Interrupted tour reopens at step one", true);
  await page.getByRole("button", { name: "Close tour", exact: true }).click();
  // Delay a real server response; do not replace or fabricate it.
  await page.route("**/v1/victim/demo-customers", async (route) => {
    await new Promise((r) => setTimeout(r, 6000));
    await route.continue();
  });
  await page.reload();
  await page.getByRole("button", { name: "Tour", exact: true }).click();
  await page.getByRole("button", { name: /Next/ }).click();
  await page.waitForTimeout(3000);
  check(
    "Slow real response shows tour loader",
    await page.getByText(/Preparing this step/).isVisible(),
  );
  check(
    "Slow real response avoids premature missing-panel warning",
    (await page
      .getByText(/This panel is not on the current screen yet/)
      .count()) === 0,
  );
  await shot("tour-loading");
  await page.locator(".customer-option").first().waitFor({ timeout: 30000 });
  await page.unroute("**/v1/victim/demo-customers");
  for (const width of [390, 574, 1242]) {
    await page.setViewportSize({ width, height: 668 });
    const footer = await page.locator(".tour-footer").boundingBox();
    check(
      width + "px tour footer remains inside viewport",
      footer.y >= 0 && footer.y + footer.height <= 668,
    );
    await shot("tour-footer-" + width);
  }
  await page.getByRole("button", { name: "Close tour", exact: true }).click();
  const before = await read("/v1/cases/" + cid + "/audit");
  console.log(
    "Observing existing complaint for 130 seconds without mutations.",
  );
  for (let i = 0; i < 13; i++) await page.waitForTimeout(10000);
  const after = await read("/v1/cases/" + cid + "/audit");
  const feeds = (items) =>
    items.filter((x) => x.event === "bank_feed_received").length;
  check(
    "Idle observation does not republish bank feed every two minutes",
    feeds(after) === feeds(before),
  );
  await fs.writeFile(
    new URL("idle-audit.json", out),
    JSON.stringify(
      {
        caseId: cid,
        beforeEvents: before.length,
        afterEvents: after.length,
        beforeFeeds: feeds(before),
        afterFeeds: feeds(after),
      },
      null,
      2,
    ),
  );
  check("No uncaught browser errors", errors.length === 0);
  await fs.writeFile(
    new URL("regression-results.json", out),
    JSON.stringify({ checks, audits, errors }, null, 2),
  );
} catch (e) {
  await shot("regression-failure");
  await fs.writeFile(
    new URL("regression-failure.json", out),
    JSON.stringify({ checks, audits, error: e.message, errors }, null, 2),
  );
  console.error(e.message);
  process.exitCode = 1;
} finally {
  await browser.close();
}
