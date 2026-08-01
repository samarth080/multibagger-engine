const { test, expect } = require("@playwright/test");

test.skip(({ browserName }) => browserName !== "chromium", "Visual baselines use system Chrome only.");

async function stabilizeOperationalText(page) {
  await page.evaluate(() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      walker.currentNode.nodeValue = walker.currentNode.nodeValue
        .replace(/\b[0-9a-f]{8}-[0-9a-f-]{27}\b/gi, "00000000-0000-0000-0000-000000000000")
        .replace(/\bBuild [0-9a-f]{8}\b/gi, "Build 00000000")
        .replace(/2026-08-01T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)/g, "2026-08-01T00:00:00Z");
    }
  });
}

const cases = [
  { name: "rankings-desktop-light", route: "/", viewport: { width: 1440, height: 900 }, theme: "light" },
  { name: "rankings-mobile-dark", route: "/", viewport: { width: 390, height: 844 }, theme: "dark" },
  { name: "screener-desktop-light", route: "/screener.html", viewport: { width: 1440, height: 900 }, theme: "light" },
  { name: "screener-mobile-dark", route: "/screener.html", viewport: { width: 360, height: 800 }, theme: "dark" },
  { name: "methodology-tablet-dark", route: "/methodology.html", viewport: { width: 768, height: 1024 }, theme: "dark" },
  { name: "company-desktop-light", route: "/company/aa5d17e7-8fe4-5305-960d-ec7b21aa0211.html", viewport: { width: 1440, height: 900 }, theme: "light" },
  { name: "company-mobile-dark", route: "/company/aa5d17e7-8fe4-5305-960d-ec7b21aa0211.html", viewport: { width: 390, height: 844 }, theme: "dark" },
  { name: "company-missing-financials-tablet", route: "/company/f146c1af-88ee-57c8-942c-efb3f8025dc6.html", viewport: { width: 1024, height: 768 }, theme: "light" },
  { name: "legacy-desktop-dark", route: "/reports/BLS_NS.html", viewport: { width: 1440, height: 900 }, theme: "dark" },
];

for (const item of cases) {
  test(item.name, async ({ page }) => {
    await page.setViewportSize(item.viewport);
    await page.addInitScript(value => localStorage.setItem("mbe-theme", value), item.theme);
    await page.goto(item.route);
    await page.waitForLoadState("networkidle");
    await stabilizeOperationalText(page);
    await expect(page).toHaveScreenshot(`${item.name}.png`, { fullPage: true });
  });
}

test("search-dialog-mobile-light", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.addInitScript(() => localStorage.setItem("mbe-theme", "light"));
  await page.goto("/");
  await page.getByRole("button", { name: "Search instruments" }).click();
  await page.getByRole("searchbox", { name: "Symbol, company name or ISIN" }).fill("KFINTECH");
  await stabilizeOperationalText(page);
  await expect(page.getByRole("dialog")).toHaveScreenshot("search-dialog-mobile-light.png");
});

test("mobile-navigation-dark", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.addInitScript(() => localStorage.setItem("mbe-theme", "dark"));
  await page.goto("/");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("dialog", { name: "Navigation" })).toHaveScreenshot("mobile-navigation-dark.png");
});
