import { test, expect } from "@playwright/test";
import path from "path";

// Smoke: UI renders and is keyboard-reachable without the backend.
test("home exposes the three entry points and a skip link", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await expect(page.getByRole("searchbox", { name: "Search the catalog" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Upload audio" })).toBeVisible();
});

// Full journey: requires `docker compose up`, an ingested catalog, and E2E_AUDIO=/path/to/clip.mp3 (a file you are authorized to use).
test("upload -> select section -> find similar", async ({ page }) => {
  test.skip(!process.env.E2E_AUDIO, "set E2E_AUDIO to run the backend journey");
  await page.goto("/");
  await page.getByLabel("I’m authorized to use this audio").check();
  await page.setInputFiles('input[type="file"]', path.resolve(process.env.E2E_AUDIO!));
  await expect(page.getByRole("button", { name: "Select a section" })).toBeVisible({ timeout: 90_000 });
  await page.getByRole("button", { name: "Select a section" }).click();
  await page.getByRole("button", { name: "Find similar" }).click();
  await expect(page.getByText(/Searching|Analyzing|No close matches|Match/).first()).toBeVisible({ timeout: 90_000 });
});
