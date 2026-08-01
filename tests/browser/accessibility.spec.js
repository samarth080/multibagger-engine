const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

const routes = [
  ["rankings", "/"],
  ["screener", "/screener.html"],
  ["methodology", "/methodology.html"],
  ["company-complete", "/company/aa5d17e7-8fe4-5305-960d-ec7b21aa0211.html"],
  ["company-missing-financials", "/company/f146c1af-88ee-57c8-942c-efb3f8025dc6.html"],
  ["legacy", "/reports/BLS_NS.html"],
];

test.describe("automated WCAG 2.2 AA audit", () => {
  test.skip(({ browserName }) => browserName !== "chromium", "One deterministic axe pass is sufficient; engine journeys run separately.");
  for (const [name, route] of routes) {
    for (const theme of ["light", "dark"]) {
      test(`${name} · ${theme}`, async ({ page }) => {
        await page.addInitScript(value => localStorage.setItem("mbe-theme", value), theme);
        await page.goto(route);
        await page.waitForLoadState("networkidle");
        const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
        const serious = results.violations.filter(item => ["serious", "critical"].includes(item.impact)).map(item => ({
          id: item.id,
          impact: item.impact,
          targets: item.nodes.map(node => node.target.join(" ")),
        }));
        expect(serious).toEqual([]);
      });
    }
  }

  for (const [name, route] of routes.slice(0, 5)) {
    test(`${name} · mobile 390px`, async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(route);
      await page.waitForLoadState("networkidle");
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
      const serious = results.violations.filter(item => ["serious", "critical"].includes(item.impact)).map(item => ({
        id: item.id,
        impact: item.impact,
        targets: item.nodes.map(node => node.target.join(" ")),
      }));
      expect(serious).toEqual([]);
    });
  }
});
