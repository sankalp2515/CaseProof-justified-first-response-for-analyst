// Accessibility scan of the guided tour dialog (intro and a spotlighted step).
import { chromium } from "playwright";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const axe = require("axe-core");
const base = process.env.CASEPROOF_BASE_URL || "http://127.0.0.1:8080";
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1366, height: 820 } });
let failures = 0;
async function scan(name) {
  await page.addScriptTag({ content: axe.source });
  const result = await page.evaluate(() =>
    axe.run(document, { runOnly: ["wcag2a", "wcag2aa"] }),
  );
  const tour = result.violations.filter((v) =>
    v.nodes.some((n) => n.target.join(" ").includes("tour")),
  );
  console.log("AXE", name, result.violations.length, "tour:", tour.length);
  for (const v of tour) console.log("  ", v.id, v.help);
  failures += tour.length;
}
await page.goto(base + "/app/#/entry");
await page.getByRole("button", { name: "Take the guided tour" }).click();
await page.getByRole("dialog").waitFor();
await scan("intro");
await page.getByRole("button", { name: /Next/ }).click();
await page.locator(".tour-spotlight").waitFor({ timeout: 15000 });
await scan("practice-step");
await browser.close();
process.exit(failures ? 1 : 0);
