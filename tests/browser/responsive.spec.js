const { test, expect } = require("@playwright/test");

test.skip(({ browserName }) => browserName !== "chromium", "Responsive matrix uses system Chrome; cross-engine journeys are separate.");

const viewports = [
  ["desktop", 1440, 900], ["tablet-landscape", 1024, 768], ["tablet-portrait", 768, 1024],
  ["mobile", 390, 844], ["mobile-small", 360, 800], ["mobile-narrow", 320, 720],
];
const routes = [["rankings", "/"], ["screener", "/screener.html"], ["company", "/company/aa5d17e7-8fe4-5305-960d-ec7b21aa0211.html"]];

for (const [viewportName, width, height] of viewports) {
  for (const [routeName, route] of routes) {
    test(`${routeName} has no viewport overflow at ${viewportName}`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.goto(route);
      await page.waitForLoadState("networkidle");
      const geometry = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, content: document.documentElement.scrollWidth }));
      expect(geometry.content, JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.viewport + 1);
      if (width <= 390) {
        for (const button of await page.locator("button:visible").all()) {
          const box = await button.boundingBox();
          if (box) expect(Math.min(box.width, box.height)).toBeGreaterThanOrEqual(24);
        }
      }
    });
  }
}

for (const [name, route] of routes) {
  test(`${name} reflows at an effective 200% browser zoom`, async ({ page }) => {
    // At 200% browser zoom a 1440px display exposes roughly 720 CSS pixels,
    // which also exercises the responsive breakpoints a real zoom operation uses.
    await page.setViewportSize({ width: 720, height: 900 });
    await page.goto(route);
    const geometry = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, content: document.documentElement.scrollWidth }));
    expect(geometry.content, JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.viewport + 1);
    await expect(page.locator("main")).toBeVisible();
  });
}

test("reduced motion preference disables meaningful animation", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  await page.goto("/");
  expect(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(true);
  const duration = await page.evaluate(() => {
    const node = document.querySelector(".skeleton");
    return node ? getComputedStyle(node).animationDuration : "0s";
  });
  expect(["0s", "0.01s", "0.00001s"]).toContain(duration);
  await context.close();
});

test("server-rendered ranking content survives delayed enhancement", async ({ page }) => {
  await page.route("**/api/v1/*.json", async route => {
    await new Promise(resolve => setTimeout(resolve, 250));
    await route.continue();
  });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Multibagger Rankings" })).toBeVisible();
  await expect(page.locator("[data-ranking-rows] tr")).toHaveCount(25);
});
