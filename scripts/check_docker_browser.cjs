const { chromium } = require("playwright");
const fs = require("fs");
const base = process.env.API_BASE_URL || "http://127.0.0.1:8080";
const output = process.env.OUTPUT_DIR || "var";
fs.mkdirSync(output, { recursive: true });
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function api(path, body) {
  const response = await fetch(
    base + path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  if (!response.ok) throw Error("API " + response.status + " " + path);
  return response.json();
}
async function until(check, description) {
  for (let i = 0; i < 240; i++) {
    if (await check()) return;
    await sleep(500);
  }
  throw Error("Timed out: " + description);
}
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({
      viewport: { width: 1600, height: 1100 },
    });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(base + "/inspector?operator=1");
    await page.getByRole("heading", { name: "Cedar fraud desk" }).waitFor();
    await page.locator("#metrics[aria-busy='false']").waitFor();
    await page.screenshot({
      path: output + "/docker-dashboard.png",
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "Try demo case", exact: true })
      .click();
    await page.waitForFunction(() => location.hash.startsWith("#case="));
    const loaded = {
      case_id: new URLSearchParams(new URL(page.url()).hash.slice(1)).get(
        "case",
      ),
    };
    await until(
      async () =>
        (await api("/v1/cases/" + loaded.case_id)).ledger_matches.length > 0,
      "demo analysis",
    );
    await page.getByRole("link", { name: /Cases/ }).click();
    await page.getByLabel("Search cases").fill(loaded.case_id);
    await page
      .locator("#case-list button")
      .filter({ hasText: loaded.case_id })
      .click();
    await page.getByRole("tab", { name: "Evidence", exact: true }).click();
    await page.waitForSelector("#facts .source-chip");
    await page
      .locator("#facts .source-chip")
      .filter({ hasText: "receipt" })
      .first()
      .click();
    await page.waitForSelector(".box.selected");
    await page.screenshot({
      path: output + "/docker-workspace-desktop.png",
      fullPage: true,
    });
    if (await page.locator("#approve").isEnabled())
      throw Error("Analyst can approve");
    await page.getByRole("tab", { name: "Overview", exact: true }).click();
    await page.locator("#requests button").click();
    await page.waitForSelector("#customer-link:not([hidden])");
    await until(
      () =>
        page
          .getByRole("button", { name: "Recreate customer request link" })
          .isEnabled(),
      "request control reenabled",
    );
    const customer = await browser.newPage({
      viewport: { width: 390, height: 844 },
    });
    customer.on("pageerror", (error) =>
      errors.push("Customer: " + error.message),
    );
    const customerPath = new URL(
      await page.locator("#customer-link").getAttribute("href"),
    ).pathname;
    await customer.goto(base + customerPath);
    await customer.waitForFunction(
      () => !document.getElementById("customer-form").hidden,
    );
    await customer.locator("#customer-submit").click();
    await customer
      .getByText("Add a file or write a response before submitting.")
      .waitFor();
    await customer
      .locator("#customer-notes")
      .fill(
        "I confirm another transfer of INR 25,000 on 2026-10-01 at 11:41 " +
          "to refund-desk@fictional.invalid. The caller asked for a refund verification payment.",
      );
    await customer.screenshot({
      path: output + "/docker-customer-mobile.png",
      fullPage: true,
    });
    const formOverflow = await customer.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    );
    await customer.locator("#customer-submit").click();
    await customer.waitForFunction(() =>
      document
        .getElementById("customer-status")
        .textContent.includes("response was received"),
    );
    await until(
      async () =>
        (await api("/v1/cases/" + loaded.case_id)).readiness.disposition ===
        "COMPLETE_CANDIDATE",
      "customer processing",
    );
    // The analyst must see the customer's new revision without a manual pipeline/refresh click.
    await page.waitForFunction(
      () =>
        document
          .getElementById("readiness")
          .textContent.includes("Complete candidate"),
      undefined,
      { timeout: 30000 },
    );
    await page.getByRole("tab", { name: "Activity", exact: true }).click();
    await page.locator("#diff").click();
    await page.waitForFunction(() =>
      document
        .getElementById("change-summary")
        .textContent.includes("Comparing revision"),
    );
    await page
      .getByRole("tab", { name: "Review & decision", exact: true })
      .click();
    if (await page.locator("#approve").isEnabled())
      throw Error("Analyst can approve");
    await page.locator("#role").selectOption("reviewer");
    await page.locator("#approve").click();
    await page
      .getByText("Enter a review reason describing what you checked.")
      .waitFor();
    await page
      .locator("#reason")
      .fill("Checked both sourced debits and the local money trail.");
    await page.locator("#approve").click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Cancel", exact: true })
      .click();
    if ((await api("/v1/cases/" + loaded.case_id + "/workflow")).approval)
      throw Error("Cancel recorded an approval");
    await page.locator("#approve").click();
    await api("/v1/cases/" + loaded.case_id + "/upload-links", {});
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Confirm approval" })
      .click();
    await page
      .getByText(
        "This case changed or needs a current approval. Review the latest evidence and approve again before sending.",
        { exact: true },
      )
      .waitFor();
    if ((await api("/v1/cases/" + loaded.case_id + "/workflow")).approval)
      throw Error("Stale decision approved");
    await page.locator("#approve").click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Confirm approval" })
      .click();
    await page.waitForFunction(() =>
      document.getElementById("status").textContent.includes("recorded for"),
    );
    await page.locator("#export").click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Send simulated reports" })
      .click();
    await page.waitForFunction(() =>
      document.getElementById("status").textContent.includes("acknowledged"),
    );
    const downloadEvent = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "Download case packet", exact: true })
      .click();
    const download = await downloadEvent;
    const downloaded = JSON.parse(
      fs.readFileSync(await download.path(), "utf8"),
    );
    if (
      downloaded.revision !==
      (await api("/v1/cases/" + loaded.case_id)).revision
    )
      throw Error("Wrong downloaded revision");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: output + "/docker-workspace-mobile.png",
      fullPage: true,
    });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    );
    const customerOverflow = await customer.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    );
    await page.getByRole("tab", { name: "Overview", exact: true }).click();
    await page.setViewportSize({ width: 1600, height: 1100 });
    await page.screenshot({
      path: output + "/docker-workspace-desktop.png",
      fullPage: true,
    });
    // A genuinely new complaint: employee creates it; customer uploads; no bank match is fabricated.
    const fresh = await browser.newPage({
      viewport: { width: 1280, height: 950 },
    });
    fresh.on("pageerror", (error) =>
      errors.push("New complaint: " + error.message),
    );
    await fresh.goto(base + "/");
    await fresh.locator("#new-case").click();
    await fresh
      .getByLabel("Customer account", { exact: true })
      .fill("SYNTH-UX-" + Date.now());
    await fresh
      .getByRole("button", { name: "Create complaint", exact: true })
      .click();
    await fresh.waitForFunction(() => location.hash.startsWith("#case="));
    const freshId = new URLSearchParams(new URL(fresh.url()).hash.slice(1)).get(
      "case",
    );
    await fresh.locator("#upload-link").click();
    await fresh
      .getByRole("link", { name: "Open customer link", exact: true })
      .waitFor();
    await until(
      () => fresh.locator("#next-step button").isEnabled(),
      "next action reenabled",
    );
    const reply = await browser.newPage({
      viewport: { width: 390, height: 844 },
    });
    reply.on("pageerror", (error) => errors.push("Upload: " + error.message));
    await reply.goto(
      base +
        new URL(await fresh.locator("#customer-link").getAttribute("href"))
          .pathname,
    );
    await reply.locator("#customer-form:not([hidden])").waitFor();
    await reply.locator("#customer-file").setInputFiles({
      name: "statement.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("not supported"),
    });
    await reply
      .getByText(
        "Choose a PNG, JPEG or UTF-8 text file. PDF documents are not supported.",
      )
      .waitFor();
    await reply.locator("#customer-file").setInputFiles({
      name: "fake.png",
      mimeType: "image/png",
      buffer: Buffer.from("not an image"),
    });
    await reply.locator("#customer-submit").click();
    await reply.waitForFunction(() =>
      document
        .getElementById("customer-error")
        .textContent.includes("could not be accepted"),
    );
    await reply
      .getByRole("button", { name: "Remove fake.png", exact: true })
      .click();
    await reply.locator("#customer-kind").selectOption("narrative");
    await reply.locator("#customer-file").setInputFiles({
      name: "statement.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(
        "INR 50000 was debited on 2026-10-15 at 11:29. Reference SYNTH-TX-50000. I did not authorize this payment.",
      ),
    });
    await reply.locator("#customer-submit").click();
    await reply
      .getByRole("heading", {
        name: "Thank you. Your response is received.",
        exact: true,
      })
      .waitFor();
    await reply.screenshot({
      path: output + "/docker-customer-receipt.png",
      fullPage: true,
    });
    await until(
      async () => (await api("/v1/cases/" + freshId)).claims.length > 0,
      "new complaint processing",
    );
    const freshSnapshot = await api("/v1/cases/" + freshId);
    if (
      freshSnapshot.ledger_matches.length ||
      freshSnapshot.readiness.disposition !== "REVIEW_REQUIRED"
    )
      throw Error("New complaint fabricated bank verification");
    await fresh
      .getByRole("tab", { name: "Review & decision", exact: true })
      .click();
    await fresh.locator("#role").selectOption("reviewer");
    if (await fresh.locator("#approve").isEnabled())
      throw Error("Incomplete complaint can be approved");
    await reply.reload();
    await reply
      .getByText(
        "This private link is closed or expired. Ask the fraud desk for a new link.",
        { exact: true },
      )
      .waitFor();
    await page.getByRole("tab", { name: "Activity", exact: true }).click();
    await page.locator("#diff").click();
    await page.waitForFunction(() =>
      document
        .getElementById("change-summary")
        .textContent.includes("Comparing revision"),
    );
    await page.getByRole("link", { name: /Cases/ }).click();
    await page.getByLabel("Search cases").fill(freshId);
    await page
      .locator("#case-list button")
      .filter({ hasText: freshId })
      .click();
    await page.getByRole("tab", { name: "Activity", exact: true }).click();
    if (
      (await page.locator("#change-summary").textContent()).trim() ||
      (await page.locator("#diff-details").isVisible())
    )
      throw Error("Previous case comparison leaked into a different case");
    // Hold an actual mutation response while the user navigates away.
    await fresh.locator("#role").selectOption("analyst");
    await fresh.getByRole("tab", { name: "Overview", exact: true }).click();
    let releaseResponse, requestArrived;
    const held = new Promise((resolve) => (releaseResponse = resolve));
    const arrived = new Promise((resolve) => (requestArrived = resolve));
    await fresh.route(
      "**/v1/cases/" + freshId + "/upload-links",
      async (route) => {
        const response = await route.fetch();
        requestArrived();
        await held;
        await route.fulfill({ response });
      },
    );
    await fresh.locator("#upload-link").click();
    await arrived;
    await fresh.getByRole("link", { name: "Dashboard", exact: true }).click();
    releaseResponse();
    await until(
      () => fresh.locator("#upload-link").isEnabled(),
      "mutation completed after navigation",
    );
    if (
      !(await fresh.locator("#dashboard-page").isVisible()) ||
      (await fresh.locator("#case-page").isVisible())
    )
      throw Error("Late case mutation replaced the dashboard");
    const result = {
      passed: !errors.length && !overflow && !customerOverflow && !formOverflow,
      case_id: loaded.case_id,
      errors,
      mobile_overflow: overflow,
      customer_mobile_overflow: customerOverflow,
      customer_form_overflow: formOverflow,
      workflow: "OCR > request > customer reply > approve > send",
      new_complaint_id: freshId,
      checks: [
        "root dashboard",
        "demo entry",
        "case search",
        "source image box",
        "automatic reply refresh",
        "empty response",
        "cancel approval",
        "required review reason",
        "stale approval rejected and refreshed",
        "confirmed approval and send",
        "packet download",
        "new complaint upload link",
        "PDF rejected",
        "bad image rejected",
        "upload retry",
        "receipt confirmation",
        "incomplete case cannot approve",
        "closed link rejected",
        "request control reenabled",
        "next action reenabled",
        "comparison scoped to current case",
        "navigation preserved during mutation",
      ],
    };
    fs.writeFileSync(
      output + "/docker_browser_validation.json",
      JSON.stringify(result, null, 2),
    );
    console.log(JSON.stringify(result));
    if (!result.passed) throw Error("Browser validation failed");
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
