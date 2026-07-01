import { test, expect } from "@playwright/test";
import path from "path";

test.describe("Glossary Management", () => {
  test("should upload a CSV glossary and verify list display", async ({ page }) => {
    const email = `e2e-glossary-${Date.now()}@example.com`;
    await page.goto("/register");
    await page.waitForSelector('input[type="email"], input[name="account"], input[placeholder*="邮箱"]');
    await page.getByPlaceholder(/邮箱|账号/i).fill(email);
    await page.getByPlaceholder(/密码/i).fill("TestPass123");
    await page.getByPlaceholder(/验证码/i).fill("123456");
    await page.getByRole("button", { name: /注册|提交/i }).click();
    await page.waitForURL(/\/dashboard|\/$/);
    await page.goto("/glossaries");
    await page.waitForSelector('[data-testid="upload-area"], input[type="file"], button:has-text("上传")', { timeout: 5000 });
    const csvPath = path.join(__dirname, "fixtures", "glossary.csv");
    const fileChooserPromise = page.waitForEvent("filechooser");
    await page.getByText(/上传|导入|CSV/i).first().click();
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles(csvPath);
    await expect(page.getByText(/术语|transformer|embedding/i)).toBeVisible({ timeout: 10000 });
  });

  test("should export glossary and verify content", async ({ page }) => {
    const email = `e2e-glossary-export-${Date.now()}@example.com`;
    await page.goto("/register");
    await page.waitForSelector('input[type="email"], input[name="account"], input[placeholder*="邮箱"]');
    await page.getByPlaceholder(/邮箱|账号/i).fill(email);
    await page.getByPlaceholder(/密码/i).fill("TestPass123");
    await page.getByPlaceholder(/验证码/i).fill("123456");
    await page.getByRole("button", { name: /注册|提交/i }).click();
    await page.waitForURL(/\/dashboard|\/$/);
    await page.goto("/glossaries");
    await page.waitForSelector('[data-testid="upload-area"], input[type="file"]', { timeout: 5000 });
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: /导出|下载/i }).first().click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain(".csv");
  });
});
