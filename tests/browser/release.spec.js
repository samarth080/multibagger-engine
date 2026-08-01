const { test, expect } = require("@playwright/test");

const BLS_ID = "aa5d17e7-8fe4-5305-960d-ec7b21aa0211";

test("primary navigation, keyboard search and company journey", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Multibagger Rankings" })).toBeVisible();
  await page.keyboard.press("ControlOrMeta+K");
  const dialog = page.getByRole("dialog", { name: "Search instruments" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("searchbox").fill("BLS");
  await expect(dialog.getByRole("option")).toHaveCount(1);
  await dialog.getByRole("searchbox").press("ArrowDown");
  await dialog.getByRole("searchbox").press("Enter");
  await expect(page).toHaveURL(new RegExp(`/company/${BLS_ID}\\.html$`));
  await expect(page.getByRole("heading", { level: 1, name: /BLS International/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Why this company ranks here" })).toBeVisible();
  const peer = page.locator(".peer-table a").first();
  const peerHref = await peer.getAttribute("href");
  await peer.click();
  await expect(page).toHaveURL(new RegExp(`${peerHref.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&")}$`));
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`/company/${BLS_ID}\\.html$`));
});

test("rankings filters, sorting, columns and export remain operable", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("[data-mode-badge]")).toContainText(/Static|snapshot/i);
  await page.getByLabel("Company search").fill("BLS");
  await page.getByRole("button", { name: "Update rankings" }).click();
  await expect(page.locator("[data-result-count]")).toContainText("1");
  await page.getByRole("button", { name: /MB score/ }).click();
  await expect(page.locator('th[data-column="score"]')).toHaveAttribute("aria-sort", /ascending|descending/);
  await page.getByRole("button", { name: "Columns" }).click();
  await expect(page.locator("[data-column-popover]")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export filtered CSV" }).click();
  await expect((await download).suggestedFilename()).toMatch(/^multibagger-rankings-/);
});

test("screener preset, custom condition, URL restoration and export", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/screener.html");
  await expect(page.locator("[data-screener-count]")).toContainText("250");
  await page.getByRole("button", { name: "High Confidence Candidates" }).click();
  await expect(page.locator("[data-condition-count]")).toContainText("1 active");
  await page.getByLabel("Field", { exact: true }).selectOption("multibagger_score");
  await page.getByLabel("Operator").selectOption("gte");
  await page.getByLabel(/Value/).fill("70");
  await page.getByRole("button", { name: "Add condition" }).click();
  await expect(page.locator("[data-condition-count]")).toContainText("2 active");
  await page.getByRole("button", { name: "Edit" }).last().click();
  await page.getByLabel(/Value/).fill("75");
  await page.getByRole("button", { name: "Update condition" }).click();
  await page.getByRole("button", { name: "Copy screen link" }).click();
  await expect(page.locator("[data-share-screen]")).toContainText("Link copied");
  expect(new URL(page.url()).searchParams.get("screen")).toBeTruthy();
  await page.reload();
  await expect(page.locator("[data-condition-count]")).toContainText("2 active");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  await expect((await download).suggestedFilename()).toMatch(/^mbe-screen-/);
  await page.getByRole("button", { name: /Remove Multibagger Score/ }).click();
  await expect(page.locator("[data-condition-count]")).toContainText("1 active");
});

test("company checklist persists, resets and copy feedback is announced", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto(`/company/${BLS_ID}.html`);
  const first = page.locator("[data-checklist-item]").first();
  await first.check();
  await expect(page.locator("[data-checklist-status]")).toContainText("1 of 9");
  await page.reload();
  await expect(page.locator("[data-checklist-item]").first()).toBeChecked();
  await page.getByRole("button", { name: "Copy link" }).click();
  await expect(page.getByRole("button", { name: "Link copied" })).toBeVisible();
  await page.getByRole("button", { name: "Reset checklist" }).click();
  await expect(page.locator("[data-checklist-status]")).toContainText("0 of 9");
});

test("legacy route declares the immutable company route as canonical", async ({ page }) => {
  await page.goto("/reports/BLS_NS.html");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", `https://multibagger-engine.vercel.app/company/${BLS_ID}.html`);
  await expect(page.getByRole("heading", { level: 1, name: /BLS International/ })).toBeVisible();
});

test("not-found document is useful and excluded from indexing", async ({ page }) => {
  const response = await page.goto("/404.html");
  expect(response.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "This research page could not be found" })).toBeVisible();
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  await expect(page.getByRole("link", { name: "Return to rankings" })).toBeVisible();
});

test("mobile navigation traps focus, closes with Escape and restores focus", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "Open navigation" });
  await trigger.click();
  const drawer = page.getByRole("dialog", { name: "Navigation" });
  await expect(drawer).toBeVisible();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Escape");
  await expect(drawer).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
});

test("static content remains useful with JavaScript disabled", async ({ browserName, browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Multibagger Rankings" })).toBeVisible();
  await expect(page.locator("[data-ranking-rows] tr")).toHaveCount(25);
  await page.goto(`/company/${BLS_ID}.html`);
  await expect(page.getByRole("heading", { name: "Financial summary" })).toBeVisible();
  await context.close();
  expect(browserName).toBeTruthy();
});

test("explicit API mode shows an accessible unavailable state without destroying static navigation", async ({ page }) => {
  await page.route("**/", async route => {
    const response = await route.fetch();
    const body = (await response.text()).replace('data-data-mode="static"', 'data-data-mode="api"');
    await route.fulfill({ response, body, headers: { ...response.headers(), "content-type": "text/html; charset=utf-8" } });
  });
  await page.goto("/");
  await expect(page.locator("[data-table-state]")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Rankings unavailable" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeVisible();
});
