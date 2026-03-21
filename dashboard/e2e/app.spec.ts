import { test, expect } from "@playwright/test";

test("dashboard loads successfully", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/fineract/i);
});

test("navigation is visible", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("nav")).toBeVisible();
});
