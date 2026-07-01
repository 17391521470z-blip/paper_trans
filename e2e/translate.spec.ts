import { test, expect } from "@playwright/test";
import path from "path";

test.describe("Translation Flow", () => {
  test("should upload PDF and start translation", async ({ page }) => {
    const email = `e2e-trans-${Date.now()}@example.com`;
    await page.goto("/register");
    await page.waitForSelector('input[type="email"], input[name="account"], input[placeholder*="邮箱"]');
    await page.getByPlaceholder(/邮箱|账号/i).fill(email);
    await page.getByPlaceholder(/密码/i).fill("TestPass123");
    await page.getByPlaceholder(/验证码/i).fill("123456");
    await page.getByRole("button", { name: /注册|提交/i }).click();
    await page.waitForURL(/\/dashboard|\/$/);
    await page.goto("/translate");
    await page.waitForSelector('input[type="file"], [data-testid="file-input"]', { timeout: 5000 });
    const fileChooserPromise = page.waitForEvent("filechooser");
    await page.getByText(/上传|选择文件|拖拽/i).first().click();
    const fileChooser = await fileChooserPromise;
    const pdfPath = path.join(__dirname, "fixtures", "sample.pdf");
    await fileChooser.setFiles(pdfPath);
    await page.getByRole("button", { name: /翻译|开始/i }).click();
    await expect(page.getByText(/翻译中|进度|100%/i)).toBeVisible({ timeout: 30000 });
  });

  test("should show download button after translation completes", async ({ page }) => {
    const email = `e2e-dl-${Date.now()}@example.com`;
    await page.goto("/register");
    await page.waitForSelector('input[type="email"], input[name="account"], input[placeholder*="邮箱"]');
    await page.getByPlaceholder(/邮箱|账号/i).fill(email);
    await page.getByPlaceholder(/密码/i).fill("TestPass123");
    await page.getByPlaceholder(/验证码/i).fill("123456");
    await page.getByRole("button", { name: /注册|提交/i }).click();
    await page.waitForURL(/\/dashboard|\/$/);
    await page.goto("/translate");
    await page.waitForSelector('input[type="file"], [data-testid="file-input"]', { timeout: 5000 });
    const fileChooserPromise = page.waitForEvent("filechooser");
    await page.getByText(/上传|选择文件|拖拽/i).first().click();
    const fileChooser = await fileChooserPromise;
    const pdfPath = path.join(__dirname, "fixtures", "sample.pdf");
    await fileChooser.setFiles(pdfPath);
    await page.getByRole("button", { name: /翻译|开始/i }).click();
    await expect(page.getByRole("button", { name: /下载/i })).toBeVisible({ timeout: 60000 });
  });
});
