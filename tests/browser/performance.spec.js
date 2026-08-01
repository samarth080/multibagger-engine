const fs = require("node:fs");
const path = require("node:path");
const { test, expect } = require("@playwright/test");

test.skip(({ browserName }) => browserName !== "chromium", "Performance laboratory uses system Chrome.");

for (const [name, route] of [["rankings", "/"], ["screener", "/screener.html"], ["company", "/company/aa5d17e7-8fe4-5305-960d-ec7b21aa0211.html"], ["methodology", "/methodology.html"]]) {
  test(`${name} rendering budget`, async ({ page }) => {
    await page.addInitScript(() => {
      globalThis.__mbePerf = { cls: 0, lcp: 0, longTasks: [] };
      new PerformanceObserver(list => { for (const entry of list.getEntries()) globalThis.__mbePerf.lcp = entry.startTime; }).observe({ type: "largest-contentful-paint", buffered: true });
      new PerformanceObserver(list => { for (const entry of list.getEntries()) if (!entry.hadRecentInput) globalThis.__mbePerf.cls += entry.value; }).observe({ type: "layout-shift", buffered: true });
      new PerformanceObserver(list => { for (const entry of list.getEntries()) globalThis.__mbePerf.longTasks.push(entry.duration); }).observe({ type: "longtask", buffered: true });
    });
    const response = await page.goto(route);
    await page.waitForLoadState("networkidle");
    const metrics = await page.evaluate(() => {
      const navigation = performance.getEntriesByType("navigation")[0];
      const paint = Object.fromEntries(performance.getEntriesByType("paint").map(entry => [entry.name, entry.startTime]));
      return { ...globalThis.__mbePerf, fcp: paint["first-contentful-paint"] || 0, domContentLoaded: navigation.domContentLoadedEventEnd, transfer: navigation.transferSize, resources: performance.getEntriesByType("resource").length };
    });
    expect(response.status()).toBe(200);
    expect(metrics.lcp).toBeLessThan(2500);
    expect(metrics.cls).toBeLessThanOrEqual(0.1);
    const totalBlockingTime = metrics.longTasks.reduce((total, value) => total + Math.max(0, value - 50), 0);
    expect(totalBlockingTime, JSON.stringify(metrics)).toBeLessThanOrEqual(200);
    expect(Math.max(0, ...metrics.longTasks), JSON.stringify(metrics)).toBeLessThanOrEqual(100);
    expect(metrics.resources).toBeLessThanOrEqual(8);
  });
}

test("static asset and company payload budgets", async () => {
  const root = path.resolve(__dirname, "../..");
  const size = relative => fs.statSync(path.join(root, relative)).size;
  expect(size("site/assets/app.css")).toBeLessThanOrEqual(40 * 1024);
  expect(size("site/assets/app.js")).toBeLessThanOrEqual(60 * 1024);
  expect(size("site/assets/screener.js")).toBeLessThanOrEqual(50 * 1024);
  expect(size("site/assets/research.js")).toBeLessThanOrEqual(50 * 1024);
  const company = fs.readdirSync(path.join(root, "site/company")).filter(name => name.endsWith(".html")).map(name => size(`site/company/${name}`));
  const research = fs.readdirSync(path.join(root, "site/api/v1/research")).filter(name => name.endsWith(".json")).map(name => size(`site/api/v1/research/${name}`));
  expect(company).toHaveLength(250);
  expect(research).toHaveLength(250);
  expect(Math.max(...company)).toBeLessThanOrEqual(35 * 1024);
  expect(Math.max(...research)).toBeLessThanOrEqual(32 * 1024);
});
