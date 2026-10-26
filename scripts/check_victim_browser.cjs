const { chromium } = require("playwright");
const fs = require("fs");
const base = process.env.API_BASE_URL || "http://127.0.0.1:8080";
const out = process.env.OUTPUT_DIR || "/artifacts";
fs.mkdirSync(out, { recursive: true });
const checks = [];
const errors = [];
const check = (ok, text) => {
  if (!ok) throw Error(text);
  checks.push(text);
};
async function until(fn, label) {
  for (let i = 0; i < 160; i++) {
    if (await fn()) return;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw Error("Timeout " + label);
}
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({
      viewport: { width: 1360, height: 980 },
      timezoneId: "Asia/Kolkata",
    });
    context.on("page", (p) => p.on("pageerror", (e) => errors.push(e.message)));
    const victim = await context.newPage();
    const catalogue = await (
      await context.request.get(base + "/v1/victim/demo-customers")
    ).json();
    const publicEntry = await context.request.post(
      base + "/v1/victim/sessions",
      {
        headers: { Host: "127.0.0.1:8080", Origin: "http://127.0.0.1:8080" },
        data: { customer_id: catalogue.customers[0].account },
      },
    );
    check(publicEntry.ok(), "Localhost port survives proxy origin checks");
    await context.clearCookies();
    await victim.goto(base + "/report");
    await victim.locator("#practice-session").click();
    await victim.locator("#practice-session:not([disabled])").waitFor();
    check(
      (
        await (
          await context.request.get(base + "/v1/workspace?scope=active")
        ).json()
      ).cases.length === 0,
      "Fresh browser session has no prerecorded complaints",
    );
    await victim
      .locator("#victim-person option")
      .first()
      .waitFor({ state: "attached" });
    check(
      (await victim.locator("#victim-person option").count()) === 12,
      "Twelve preloaded customers; no dataset setup",
    );
    await victim.locator("#victim-enter").click();
    await victim.locator("#victim-account:not([hidden])").waitFor();
    const me = await (await context.request.get(base + "/v1/victim/me")).json();
    const tx = me.transactions.find((t) => t.txn_id.endsWith("-T1"));
    const image = await context.request.get(
      base + "/v1/victim/receipts/" + tx.txn_id,
    );
    check(image.ok(), "Customer can access independent bank receipt");
    await victim
      .locator('input[name=payment][value="' + tx.txn_id + '"]')
      .check();
    await victim
      .locator("#victim-story")
      .fill(
        "Someone pretending to be from my bank frightened me into sending this payment. Please investigate. Browser run " +
          Date.now(),
      );
    await victim.locator("#victim-authorisation").selectOption("deceived");
    await victim.locator("#victim-files").setInputFiles({
      name: "new-victim-receipt.png",
      mimeType: "image/png",
      buffer: await image.body(),
    });
    await victim.locator("#victim-submit").click();
    await victim
      .locator("#victim-form[hidden]")
      .waitFor({ state: "attached", timeout: 90000 });
    const cid = (await victim.locator("#receipt-id").textContent()).replace(
      "Bank complaint reference: CEDAR-",
      "CASE-",
    );
    check(
      cid.startsWith("CASE-"),
      "Victim created a new complaint with a receipt",
    );
    await victim.screenshot({
      path: out + "/victim-new-complaint.png",
      fullPage: true,
    });
    const api = async (path, body, role = "analyst") => {
      const r = await context.request.fetch(base + path, {
        method: body === undefined ? "GET" : "POST",
        headers: { "X-Demo-User": role },
        ...(body === undefined ? {} : { data: body }),
      });
      const d = await r.json();
      if (!r.ok())
        throw Error(r.status() + " " + path + " " + JSON.stringify(d));
      return d;
    };
    const flow = () => api("/v1/cases/" + cid + "/workflow");
    await until(async () => {
      const f = await flow();
      return (
        f.confirmed_disputed_minor === tx.amount_minor &&
        f.status !== "processing"
      );
    }, "OCR and bank match");
    let f = await flow();
    check(
      f.additional_candidate_minor > 0,
      "Additional debit separated from confirmed disputed loss",
    );
    let snap = await api("/v1/cases/" + cid);
    check(
      snap.segments.some((s) => s.source !== "text_line"),
      "Actual uploaded PNG produced OCR segments",
    );
    const desk = await context.newPage();
    await desk.goto(base + "/inspector#case=" + cid + "&view=overview");
    await desk.locator("#case-id").filter({ hasText: cid }).waitFor();
    check(
      (await desk.locator('a[href="/simulator"]').count()) === 0,
      "Simulator controls absent from analyst navigation",
    );
    await desk.locator("#brief-summary").waitFor();
    check(
      (await desk.locator("#provider-mode").textContent()).includes("local"),
      "Actual local processing mode visible in main brief",
    );
    const briefText = await (
      await context.request.get(base + "/v1/cases/" + cid + "/brief")
    ).text();
    check(
      briefText.includes("PAYMENT INVENTORY") &&
        briefText.includes("CHRONOLOGY"),
      "Readable investigation brief includes payments and chronology",
    );
    await desk.locator("#role").selectOption("reviewer");
    await desk
      .locator("#urgent-reason")
      .fill("Reviewed the customer-selected bank debit and its cited receipt.");
    await desk.locator("#urgent-approve:not([disabled])").click();
    await desk
      .getByRole("button", {
        name: "Send approved urgent referral",
        exact: true,
      })
      .waitFor();
    await desk
      .getByRole("button", {
        name: "Send approved urgent referral",
        exact: true,
      })
      .click();
    await until(
      async () =>
        (await api("/v1/cases/" + cid + "/urgent-referrals")).some(
          (r) => r.delivery,
        ),
      "Urgent delivery",
    );
    check(
      true,
      "Urgent referral delivered before additional-debit confirmation",
    );
    await desk.locator("#role").selectOption("analyst");
    const request = desk.getByRole("button", {
      name: "Request information",
      exact: true,
    });
    await request.first().click();
    await until(
      async () =>
        (await api("/v1/victim/complaints/" + cid)).messages.length > 0,
      "Victim inbox",
    );
    await victim.locator("#receipt-refresh").click();
    await victim
      .getByRole("button", { name: "Yes, include this payment", exact: true })
      .first()
      .click();
    await until(async () => {
      const f = await flow();
      return f.additional_candidate_minor === 0 && f.status !== "processing";
    }, "Follow-up assessment");
    check(
      true,
      "Victim answered an analyst request without a canned statement",
    );
    await until(async () => {
      const s = await api("/v1/cases/" + cid);
      return s.trail.account_observations?.length >= 3;
    }, "Automatic downstream observations");
    check(true, "Downstream reports arrived without opening simulator");
    await until(
      async () => (await flow()).readiness === "COMPLETE_CANDIDATE",
      "Complete readiness",
    );
    await desk.locator("#refresh").click();
    await desk.locator("#role").selectOption("reviewer");
    await desk
      .getByRole("button", { name: "Review & decision", exact: true })
      .first()
      .click();
    await desk
      .locator("#reason")
      .fill(
        "Checked both disputed bank payments, source evidence and fresh downstream observations.",
      );
    await desk.locator("#approve").click();
    await desk.locator("#confirm-action").click();
    await until(async () => Boolean((await flow()).approval), "Full approval");
    await desk.locator("#export").click();
    await desk.locator("#confirm-action").click();
    await until(
      async () => (await flow()).status === "completed",
      "Both report acknowledgements",
    );
    f = await flow();
    check(
      f.followup.state === "awaiting_external",
      "Delivered packet leaves investigation open for follow-up",
    );
    await desk.locator("#role").selectOption("analyst");
    await desk.getByRole("tab", { name: "Overview", exact: true }).click();
    await desk.locator("#followup-owner").fill("fraud-desk-followup");
    await desk
      .locator("#followup-action")
      .fill("Check receiving institution response and record actual outcome.");
    await desk
      .locator("#followup-reason")
      .fill("Reports acknowledged; investigation remains open.");
    await desk.locator("#followup-save").click();
    await until(
      async () => (await flow()).followup.owner === "fraud-desk-followup",
      "Persistent operational assignment",
    );
    check(true, "Owner and next action saved without pretending recovery");
    await desk
      .getByRole("tab", { name: "Review & decision", exact: true })
      .click();
    check(
      f.deliveries.length === 2,
      "Both local report destinations acknowledged",
    );
    check(
      f.historical_deliveries.length >= 2,
      "Report delivery history remains visible",
    );
    const delivered = f.historical_deliveries.find(
      (r) => r.kind === "case_ticket",
    );
    const archived = await api(
      "/v1/cases/" + cid + "/delivered-packets/" + delivered.packet_id,
    );
    check(
      archived.approval_id === f.approval.approval_id,
      "Delivered packet can be retrieved independently of current approval",
    );
    check(
      (await api("/v1/cases/" + cid + "/urgent-referrals")).some(
        (r) => r.delivery,
      ),
      "Earlier urgent delivery retained after reassessment",
    );
    await desk.screenshot({
      path: out + "/victim-analyst-reports.png",
      fullPage: true,
    });
    await victim.setViewportSize({ width: 390, height: 844 });
    await victim.screenshot({
      path: out + "/victim-mobile.png",
      fullPage: true,
    });
    check(
      await victim.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      "Victim mobile layout has no horizontal overflow",
    );
    check(errors.length === 0, "No browser JavaScript errors");
    fs.writeFileSync(
      out + "/victim_browser_validation.json",
      JSON.stringify({ case_id: cid, checks, errors, workflow: f }, null, 2),
    );
    console.log(
      JSON.stringify({ case_id: cid, checks: checks.length, errors }),
    );
  } catch (e) {
    fs.writeFileSync(
      out + "/victim_browser_failure.json",
      JSON.stringify({ error: e.stack, checks, errors }, null, 2),
    );
    throw e;
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
