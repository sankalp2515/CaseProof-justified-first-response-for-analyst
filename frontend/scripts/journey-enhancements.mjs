import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const out = fileURLToPath(
  new URL("../../var/journey-validation/", import.meta.url),
);
await fs.mkdir(out, { recursive: true });
const base = "http://127.0.0.1:5178",
  browser = await chromium.launch({
    headless: true,
    args: ["--disable-gpu", "--disable-dev-shm-usage"],
  });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  reducedMotion: "reduce",
});
const page = await context.newPage(),
  checks = [],
  audits = [],
  errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const check = (name, value = true) => {
  assert.ok(value, name);
  checks.push(name);
  console.log("PASS", name);
};
const api = async (route) => {
  let r = await context.request.get(base + route, {
    headers: { "X-Demo-User": "analyst" },
  });
  assert.equal(r.status(), 200, route);
  return r.json();
};
const shot = async (name) =>
  page.screenshot({ path: path.join(out, name + ".png"), fullPage: false });
async function axe(name) {
  await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
  let result = await page.evaluate(async () => {
    let r = await axe.run(document, {
      runOnly: {
        type: "tag",
        values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"],
      },
    });
    return r.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      targets: v.nodes.map((n) => n.target),
    }));
  });
  audits.push({ name, violations: result });
  console.log("AXE", name, result.length);
}
try {
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(base + "/");
    await page
      .getByRole("heading", {
        name: "The whole case. A justified first response.",
      })
      .waitFor();
    check(
      "Landing no body overflow " + width,
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    await shot("landing-" + width);
    await axe("landing-" + width);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page
    .getByRole("link", { name: "Explore a practice case", exact: true })
    .first()
    .click();
  await page.waitForURL(/victim\/start/);
  const fresh = page.waitForResponse(
    (r) =>
      r.url().endsWith("/v1/victim/demo-session") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", {
      name: "Start a fresh practice session",
      exact: true,
    })
    .click();
  assert.equal((await fresh).status(), 200);
  await page.locator(".customer-option").filter({ hasText: "Samer" }).click();
  await page
    .getByRole("button", { name: "Continue with selected customer" })
    .click();
  await page
    .getByRole("button", { name: "Report a payment scam", exact: true })
    .click();
  await page.getByRole("checkbox", { name: /Dispute payment .*-T1$/ }).check();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page
    .getByRole("textbox", { name: "What happened?", exact: true })
    .fill(
      "A caller claiming to be bank support asked me to move money into a safe account. I made this payment after being deceived. I need the bank to investigate.",
    );
  await page.getByLabel("How did the payment happen?").selectOption("deceived");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  const mode = page.getByText("AI writing is unavailable on this local stack", {
    exact: false,
  });
  await mode.waitFor();
  check("Local AI generation is clearly unavailable", await mode.isVisible());
  for (const name of ["receipt", "chat", "call log"]) {
    const response = page.waitForResponse(
      (r) =>
        r.url().endsWith("/v1/victim/sample-evidence") &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Create synthetic " + name, exact: true })
      .click();
    assert.equal((await response).status(), 200);
  }
  await page.locator(".upload-row").nth(2).waitFor();
  await fs.writeFile(
    path.join(out, "own-call-notes.txt"),
    "I received a call from a person who claimed to be bank support and asked me to move money. These are my fictional test notes.",
  );
  await page
    .getByLabel("Report evidence", { exact: true })
    .setInputFiles(path.join(out, "own-call-notes.txt"));
  await page
    .getByLabel("Evidence kind 4", { exact: true })
    .selectOption("call_log");
  check(
    "Receipt, chat, call log and own evidence selected together",
    (await page.locator(".upload-row").count()) === 4,
  );
  await shot("multiple-evidence-desktop");
  await axe("multiple-evidence");
  await page.setViewportSize({ width: 390, height: 844 });
  await shot("multiple-evidence-mobile");
  check(
    "Multiple evidence mobile has no body overflow",
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page
    .getByRole("button", { name: "Submit report", exact: true })
    .click();
  await page.waitForURL(/victim\/complaints\/CASE-/, { timeout: 90000 });
  const cid = page.url().split("/").at(-1);
  await page
    .getByRole("button", { name: "Continue as analyst demo", exact: true })
    .click();
  await page.waitForURL(/staff\/cases/);
  check(
    "Victim confirmation opens its exact analyst case",
    page.url().includes(cid),
  );
  let workflow;
  for (let i = 0; i < 90; i++) {
    workflow = await api(`/v1/cases/${cid}/workflow`);
    if (
      !["queued", "running"].includes(workflow.job?.status) &&
      workflow.status !== "processing" &&
      !workflow.bank_data_refresh_required
    )
      break;
    await page.waitForTimeout(1500);
  }
  const snap = await api(`/v1/cases/${cid}`);
  check(
    "All five real artifacts processed",
    snap.artifacts.length === 5 &&
      snap.artifacts.every((a) =>
        snap.segments.some((s) => s.artifact_id === a.artifact_id),
      ),
  );
  check(
    "Generated evidence creates no material payment conflict",
    !snap.claims.some(
      (c) => c.materiality && c.evidence_state === "conflicted",
    ),
  );
  check(
    "Generated receipt is readable to the real OCR pipeline",
    !snap.gaps.some((g) => g.required_fact === "readable_receipt"),
  );
  check(
    "Fresh Samer complaint has actual golden-hour priority",
    workflow.clock.golden_hour_remaining > 0,
  );
  await page.getByRole("button", { name: "Money Trail", exact: true }).click();
  await page.locator(".trail-node").nth(3).waitFor({ timeout: 30000 });
  check(
    "Samer has a multi-hop bank-sourced trail",
    (await page.locator(".trail-node").count()) >= 4,
  );
  await shot("samer-trail");
  await axe("samer-trail");
  await page.getByRole("button", { name: "Tour", exact: true }).click();
  await page
    .locator(".tour-count")
    .getByText("1 / 12", { exact: true })
    .waitFor();
  check("Tour exposes twelve highlights without skipping intake");
  await page.getByRole("button", { name: "Close tour", exact: true }).click();
  await page.goto(base + `/app/#/victim/complaints/${cid}`);
  const unrelated = page.getByRole("button", {
    name: "No, this payment is unrelated",
    exact: true,
  });
  await unrelated.first().waitFor({ timeout: 30000 });
  await unrelated.first().click();
  await page
    .getByRole("button", { name: "Confirm unrelated payment", exact: true })
    .click();
  for (let i = 0; i < 60; i++) {
    workflow = await api(`/v1/cases/${cid}/workflow`);
    if (
      !workflow.bank_data_refresh_required &&
      workflow.additional_candidate_minor === 0 &&
      !["queued", "running"].includes(workflow.job?.status)
    )
      break;
    await page.waitForTimeout(1000);
  }
  await page.goto(base + `/app/#/staff/cases/${cid}/review`);
  await page
    .getByRole("combobox", { name: "Staff persona", exact: true })
    .selectOption("reviewer");
  await page
    .getByRole("textbox", { name: "Reviewer rationale", exact: true })
    .fill(
      "Reviewed the current source-linked receipt, chat, call log, own uploaded notes and bank observations. The customer excluded the separate debit. Approve only this supported synthetic revision.",
    );
  await page
    .getByRole("button", { name: "Review complete handoff", exact: true })
    .click();
  await page.getByRole("button", { name: /Approve revision / }).click();
  await page
    .getByRole("button", { name: "Delivery & follow-up", exact: true })
    .click();
  await page
    .getByRole("button", {
      name: "Review & send approved reports",
      exact: true,
    })
    .click();
  await page.getByRole("button", { name: "Confirm send", exact: true }).click();
  for (let i = 0; i < 60; i++) {
    workflow = await api(`/v1/cases/${cid}/workflow`);
    if (new Set(workflow.historical_deliveries.map((d) => d.kind)).size === 2)
      break;
    await page.waitForTimeout(1000);
  }
  check(
    "Mixed-evidence Samer complaint reaches both delivery acknowledgements",
    new Set(workflow.historical_deliveries.map((d) => d.kind)).size === 2,
  );
  const all = await api("/v1/workspace?scope=all");
  const delivered = all.cases.find(
    (c) =>
      c.case_id === cid && c.historical_deliveries?.some((d) => d.packet_id),
  );
  assert.ok(delivered);
  const pid = delivered.historical_deliveries.find(
    (d) => d.packet_id,
  ).packet_id;
  const packet = await api(
    `/v1/cases/${delivered.case_id}/delivered-packets/${pid}`,
  );
  const doc = await context.request.get(
    base + `/v1/cases/${delivered.case_id}/delivered-packets/${pid}/document`,
    { headers: { "X-Demo-User": "analyst" } },
  );
  assert.equal(doc.status(), 200);
  const html = await doc.text();
  check(
    "Document includes exact delivered revision and digest",
    html.includes(packet.audit.digest) &&
      html.includes(pid) &&
      html.includes("revision " + packet.revision),
  );
  check(
    "Handoff contains sourced money-trail positions",
    packet.report_update.traced_amounts.length > 0 &&
      packet.report_update.traced_amounts.every((p) =>
        p.path.every((id) => html.includes(id)),
      ),
  );
  await page.goto(base + `/app/#/staff/cases/${delivered.case_id}/delivery`);
  const downloaded = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download handoff document", exact: true })
    .first()
    .click();
  await (await downloaded).saveAs(path.join(out, "handoff.html"));
  check("Readable handoff downloaded through actual staff UI");
  const documentPage = await context.newPage();
  await documentPage.setContent(html);
  await documentPage
    .getByRole("heading", {
      name: "Money trail — sourced positions",
      exact: true,
    })
    .waitFor();
  await documentPage.screenshot({
    path: path.join(out, "handoff-document.png"),
    fullPage: true,
  });
  await documentPage.pdf({
    path: path.join(out, "handoff.pdf"),
    format: "A4",
    printBackground: true,
  });
  check("Readable document prints to an actual PDF");
  check("No uncaught browser errors", errors.length === 0);
  await fs.writeFile(
    path.join(out, "enhancements.json"),
    JSON.stringify(
      {
        checks,
        audits,
        errors,
        caseId: cid,
        packetId: pid,
        provider: "Tesseract + local rules; bank-simulator samples",
        liveGoogleVerified: false,
      },
      null,
      2,
    ),
  );
} catch (e) {
  await shot("enhancements-failure");
  await fs.writeFile(
    path.join(out, "enhancements-failure.json"),
    JSON.stringify({ checks, audits, errors, error: e.message }, null, 2),
  );
  console.error(e);
  process.exitCode = 1;
} finally {
  await browser.close();
}
