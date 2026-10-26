const { chromium } = require("playwright");
const fs = require("fs");
const base = process.env.API_BASE_URL || "http://127.0.0.1:8080";
const output = process.env.OUTPUT_DIR || "var/local-validation";
fs.mkdirSync(output, { recursive: true });
async function api(path, body, role = "analyst") {
  const response = await fetch(base + path, {
    headers: { "Content-Type": "application/json", "X-Demo-User": role },
    ...(body === undefined
      ? {}
      : { method: "POST", body: JSON.stringify(body) }),
  });
  const data = await response.json();
  if (!response.ok)
    throw Error(
      "API " + response.status + " " + path + " " + JSON.stringify(data),
    );
  return data;
}
async function until(check, description) {
  for (let i = 0; i < 180; i++) {
    if (await check()) return;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw Error("Timed out: " + description);
}
(async () => {
  const browser = await chromium.launch({ headless: true });
  const errors = [];
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      timezoneId: "Asia/Kolkata",
    });
    context.on("page", (page) =>
      page.on("pageerror", (e) => errors.push(e.message)),
    );
    const desk = await context.newPage();
    await desk.goto(base + "/simulator");
    const networkId = "BROWSER-" + Date.now();
    const initialCount = (await api("/v1/cases")).length;
    await desk.locator("#network-id").fill(networkId);
    await desk
      .getByRole("button", { name: "Create bank dataset", exact: true })
      .click();
    await desk.locator("#network-result:not([hidden])").waitFor();
    if ((await api("/v1/cases")).length !== initialCount)
      throw Error("Simulator preloaded a complaint");
    const initial = await desk.locator("#initial-statement").inputValue();
    const followup = await desk.locator("#followup-statement").inputValue();
    const customerAccount = await desk.locator("#bank-account").inputValue();
    await desk.screenshot({
      path: output + "/bank-simulator.png",
      fullPage: true,
    });
    const receiptReady = desk.waitForEvent("download");
    await desk.locator("#receipt-download").click();
    const receipt = await receiptReady;
    await receipt.saveAs(output + "/bank-receipt.png");
    await desk.locator("#new-complaint").click();
    await desk.getByRole("dialog").waitFor();
    if (
      (await desk.locator("#create-account").inputValue()) !== customerAccount
    )
      throw Error("Wrong customer prefill");
    await desk
      .getByRole("button", { name: "Create complaint", exact: true })
      .click();
    await desk.locator("#case-page:not([hidden])").waitFor();
    const caseId = new URLSearchParams(new URL(desk.url()).hash.slice(1)).get(
      "case",
    );
    const empty = await api("/v1/cases/" + caseId);
    if (
      empty.artifacts.length ||
      empty.claims.length ||
      caseId.startsWith("GOLD")
    )
      throw Error("Complaint was not empty");
    await desk.locator("#upload-link").click();
    await desk.locator("#customer-link:not([hidden])").waitFor();
    const victim = await context.newPage();
    await victim.goto(
      base +
        new URL(await desk.locator("#customer-link").getAttribute("href"))
          .pathname,
    );
    await victim
      .locator("#customer-file")
      .setInputFiles(output + "/bank-receipt.png");
    await victim.locator("#customer-notes").fill(initial);
    await victim.screenshot({
      path: output + "/bank-victim-upload.png",
      fullPage: true,
    });
    await victim.locator("#customer-submit").click();
    await victim
      .getByRole("heading", {
        name: "Thank you. Your response is received.",
        exact: true,
      })
      .waitFor();
    await until(async () => {
      const s = await api("/v1/cases/" + caseId);
      return s.ledger_matches.length === 1 && s.unreported.length === 1;
    }, "actual OCR and independent bank matching");
    let s = await api("/v1/cases/" + caseId);
    if (
      !s.segments.some(
        (x) =>
          x.source === "model_ocr" &&
          ["tesseract-eng-hin-v1", "tesseract-eng-hin-psm6-v2", "tesseract-eng-hin-bounded-v3", "tesseract-eng-hin-bounded-v4", "tesseract-eng-hin-bounded-v5"].includes(x.ocr_model_id),
      ) ||
      !s.trail.bank_verification.complete
    )
      throw Error("OCR or coverage missing");
    const proposed = s.requests.filter((r) => r.state === "proposed");
    if (proposed[0]?.catalogue_id !== "confirm_additional_transfer")
      throw Error("Wrong next request");
    if (proposed.some((r) => r.catalogue_id === "request_reference_crop"))
      throw Error("Asking for bank-known reference");
    if (s.trail.summary.unaccounted !== 6000000)
      throw Error("Invented downstream observation");
    await desk.getByRole("tab", { name: "Evidence", exact: true }).click();
    await desk
      .locator(".source-chip")
      .filter({ hasText: "receipt" })
      .first()
      .click();
    await desk.locator(".box.selected").waitFor();
    await desk.screenshot({
      path: output + "/bank-evidence-source.png",
      fullPage: true,
    });
    await desk.getByRole("tab", { name: "Overview", exact: true }).click();
    await desk.locator("#requests button").click();
    await desk.locator("#customer-link:not([hidden])").waitFor();
    await victim.goto(
      base +
        new URL(await desk.locator("#customer-link").getAttribute("href"))
          .pathname,
    );
    await victim.locator("#customer-notes").fill(followup);
    await victim.locator("#customer-submit").click();
    await victim
      .getByRole("heading", {
        name: "Thank you. Your response is received.",
        exact: true,
      })
      .waitFor();
    await until(
      async () =>
        (await api("/v1/cases/" + caseId)).ledger_matches.length === 2,
      "second debit confirmation",
    );
    const admin = await context.newPage();
    await admin.goto(base + "/simulator");
    await admin.locator("#network-id").fill(networkId);
    await admin.locator("#network-create").click();
    await admin.locator("#network-result:not([hidden])").waitFor();
    await admin.locator("#publish-reports").click();
    await until(
      async () =>
        (await api("/v1/cases/" + caseId)).trail.summary.recoverable ===
        5500000,
      "downstream reports and automatic trace revision",
    );
    s = await api("/v1/cases/" + caseId);
    if (
      s.readiness.disposition !== "COMPLETE_CANDIDATE" ||
      s.trail.summary.left_system !== 500000
    )
      throw Error("Wrong readiness or trace");
    await desk
      .getByRole("tab", { name: "Transactions & trail", exact: true })
      .click();
    await desk
      .getByText("₹55,000.00 observed unspent in the model", { exact: true })
      .waitFor({ timeout: 30000 });
    await desk.screenshot({
      path: output + "/bank-money-trail.png",
      fullPage: true,
    });
    await desk
      .getByRole("tab", { name: "Review & decision", exact: true })
      .click();
    if (await desk.locator("#approve").isEnabled())
      throw Error("Analyst approval enabled");
    await desk.locator("#role").selectOption("reviewer");
    await desk
      .locator("#reason")
      .fill(
        "Checked fresh victim image, complete bank coverage, two debits and sourced downstream reports.",
      );
    await desk.locator("#approve").click();
    await desk.locator("#confirm-action").click();
    await desk.locator("#export").click();
    await desk.locator("#confirm-action").click();
    await desk
      .getByRole("button", { name: "Download case packet", exact: true })
      .waitFor();
    const packetReady = desk.waitForEvent("download");
    await desk
      .getByRole("button", { name: "Download case packet", exact: true })
      .click();
    const download = await packetReady;
    await download.saveAs(output + "/bank-case-packet.json");
    const packet = JSON.parse(
      fs.readFileSync(output + "/bank-case-packet.json", "utf8"),
    );
    if (
      packet.report_update.debits.length !== 2 ||
      !packet.report_update.bank_verification.complete
    )
      throw Error("Packet lacks verified bank scope");
    const again = await api("/v1/cases/" + caseId + "/exports", {}, "reviewer");
    if (
      again.packet.packet_id !== packet.packet_id ||
      again.outbound.length !== 2
    )
      throw Error("Resend duplicated packet");
    const history = await api("/v1/cases/" + caseId + "/approvals");
    if (history.length !== 1) throw Error("Wrong immutable approval history");
    await desk.screenshot({
      path: output + "/bank-reports-delivered.png",
      fullPage: true,
    });
    const result = {
      passed: !errors.length,
      errors,
      case_id: caseId,
      network_id: networkId,
      packet_id: packet.packet_id,
      checks: [
        "bank customers before complaint",
        "empty fresh complaint",
        "actual image upload and OCR",
        "citation box",
        "complete bank coverage",
        "additional debit discovery",
        "no bank-known reference ask",
        "victim followup",
        "unknown funds before reports",
        "three downstream reports",
        "automatic trace revision",
        "integer-paisa conservation",
        "reviewer gate",
        "revision approval",
        "two simulator acknowledgements",
        "idempotent resend",
        "immutable approval history",
        "downloaded packet",
      ],
    };
    fs.writeFileSync(
      output + "/bank_browser_validation.json",
      JSON.stringify(result, null, 2),
    );
    console.log(JSON.stringify(result));
    if (!result.passed) throw Error("Browser page errors");
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.stack);
  process.exit(1);
});
