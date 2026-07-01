import { test, expect } from "@playwright/test";

test.describe("Billing Flow", () => {
  test("should visit billing page and see pricing plans", async ({ page }) => {
    const email = `e2e-billing-${Date.now()}@example.com`;
    await page.goto("/register");
    await page.waitForSelector('input[type="email"], input[name="account"], input[placeholder*="邮箱"]');
    await page.getByPlaceholder(/邮箱|账号/i).fill(email);
    await page.getByPlaceholder(/密码/i).fill("TestPass123");
    await page.getByPlaceholder(/验证码/i).fill("123456");
    await page.getByRole("button", { name: /注册|提交/i }).click();
    await page.waitForURL(/\/dashboard|\/$/);
    await page.goto("/billing");
    await page.waitForSelector('text=/标准|Pro|免费|套餐|订阅|Pricing/i', { timeout: 5000 });
    await expect(page.getByText(/标准|Pro|免费|套餐/i).first()).toBeVisible();
  });

  test("should select standard plan and proceed to payment", async ({ page }) => {
    const email = `e2e-billing2-${Date.now()}@example.com`;
    await page.goto("/register");
    await page.waitForSelector('input[type="email"], input[name="account"], input[placeholder*="邮箱"]');
    await page.getByPlaceholder(/邮箱|账号/i).fill(email);
    await page.getByPlaceholder(/密码/i).fill("TestPass123");
    await page.getByPlaceholder(/验证码/i).fill("123456");
    await page.getByRole("button", { name: /注册|提交/i }).click();
    await page.waitForURL(/\/dashboard|\/$/);
    await page.goto("/billing");
    await page.waitForSelector('text=/标准/i', { timeout: 5000 });
    await page.getByRole("button", { name: /订阅|购买|开通/i }).first().click();
    await expect(page.getByText(/支付|二维码|微信|支付宝/i)).toBeVisible({ timeout: 10000 });
  });
});
