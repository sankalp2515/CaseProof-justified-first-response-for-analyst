import { chromium } from "playwright";
import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";
const out = fileURLToPath(new URL("../../var/ux-repair/", import.meta.url));
await fs.mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1242, height: 668 } });
const base = "http://127.0.0.1:8188";
const evidence = [];
for (const width of [1242, 627]) {
  await page.setViewportSize({ width, height: 668 });
  await page.goto(base + "/app/#/staff/queue");
  await page.getByLabel("Filter cases").waitFor();
  evidence.push(
    await page.locator(".search").evaluate((e) => {
      const a = e.getBoundingClientRect(),
        b = e.querySelector("input").getBoundingClientRect();
      return {
        width: innerWidth,
        search: { x: a.x, y: a.y, width: a.width, height: a.height },
        input: { x: b.x, y: b.y, width: b.width, height: b.height },
        margin: getComputedStyle(e.querySelector("input")).margin,
      };
    }),
  );
  await page.screenshot({ path: out + `before-queue-${width}.png` });
}
await page.setViewportSize({ width: 1242, height: 668 });
await page.goto(base + "/app/#/victim/start");
await page.getByRole("button", { name: "Tour", exact: true }).click();
await page.getByRole("button", { name: /^Next/ }).click();
await page
  .getByRole("heading", {
    name: "Start your own practice session",
    exact: true,
  })
  .waitFor();
await page.waitForTimeout(1200);
evidence.push(
  await page.getByRole("dialog").evaluate((e) => {
    const r = e.getBoundingClientRect(),
      f = e.querySelector(".tour-footer").getBoundingClientRect();
    return {
      tour: { top: r.top, bottom: r.bottom, height: r.height },
      footer: { top: f.top, bottom: f.bottom },
      viewport: innerHeight,
    };
  }),
);
await page.screenshot({ path: out + "before-tour.png" });
await fs.writeFile(out + "before.json", JSON.stringify(evidence, null, 2));
console.log(JSON.stringify(evidence, null, 2));
await browser.close();
