const { chromium } = require("playwright");
const fs = require("fs");
(async () => {
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const cid = JSON.parse(fs.readFileSync("var/workspace_v3.json")).case_id;
    await page.goto("http://127.0.0.1:8000/inspector#case=" + cid);
    await page.waitForSelector(".source-chip");
    await page.locator(".source-chip").first().click();
    await page.waitForSelector(".box.selected");
  await page.locator(".box").first().click();
  await page.waitForSelector(".box.selected");
    await page.screenshot({ path: "var/inspector-v3-desktop.png", fullPage: true });
    const edges = await page.locator("#trail-svg path").count();
    if (edges < 3) throw Error("Missing trail");
    if (await page.locator("#approve").isEnabled()) throw Error("Analyst can approve");
    const clock = await page.locator("#clock-left").innerText();
    if (!clock.includes("21.0")) throw Error("Wrong clock");
    await page.locator("#queue-tab").click();
    await page.waitForSelector("#queue-body tr");
    await page.screenshot({ path: "var/inspector-v3-queue.png", fullPage: true });
    const completed = JSON.parse(fs.readFileSync("var/last_demo_mock.json")).case_id;
    await page.locator("#cases button").filter({ hasText: completed }).click();
    await page.waitForFunction(
      (id) => document.getElementById("case-id").textContent === id,
      completed,
    );
    await page.locator("#role").selectOption("reviewer");
    if (!(await page.locator("#approve").isEnabled())) throw Error("Ready reviewer cannot approve");
    await page.locator("#diff").click();
    await page.waitForSelector("#diff-result:not([hidden])");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: "var/inspector-v3-mobile.png", fullPage: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    const result = {
      errors,
      mobile_overflow: overflow,
      clock,
      edges,
      case_id: cid,
      review_case: completed,
    };
    fs.writeFileSync("var/browser_verification_v3.json", JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
    if (errors.length || overflow) throw Error("Browser check failed");
  } finally {
    if (browser) await browser.close();
  }
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
