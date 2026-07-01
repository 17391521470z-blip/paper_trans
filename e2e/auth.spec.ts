import { test, expect } from "@playwright/test";

test.describe("Authentication Flow", () => {
  test("should navigate from landing to login page", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: /开始翻译|登录/i }).first().click();
    await page.waitForURL(/\/login/);
    await expect(page.getByRole("heading", { name: /登录|注册/i })).toBeVisible();
  });

  test("should register a new user and redirect to home", async ({ page }) => {
    const email = `e2e-${Date.now()}@example.com`;
    await page.goto("/register");
    await page.waitForSelector('input[type="email"], input[name="account"], input[placeholder*="邮箱"]');
    const emailInput = page.getByPlaceholder(/邮箱|账号/i);
    await emailInput.fill(email);
    const passwordInput = page.getByPlaceholder(/密码/i);
    await passwordInput.fill("TestPass123");
    const codeInput = page.getByPlaceholder(/验证码/i);
    await codeInput.fill("123456");
    await page.getByRole("button", { name: /注册|提交/i }).click();
    await page.waitForURL(/\/dashboard|\/$/);
  });

  test("should login and verify user info consistency", async ({ page }) => {
    const email = `e2e-login-${Date.now()}@example.com`;
    await page.goto("/register");
    await page.waitForSelector('input[type="email"], input[name="account"], input[placeholder*="邮箱"]');
    await page.getByPlaceholder(/邮箱|账号/i).fill(email);
    await page.getByPlaceholder(/密码/i).fill("TestPass123");
    await page.getByPlaceholder(/验证码/i).fill("123456");
    await page.getByRole("button", { name: /注册|提交/i }).click();
    await page.waitForURL(/\/dashboard|\/$/);
    await page.goto("/login");
    await page.waitForSelector('input[type="email"], input[name="account"], input[placeholder*="邮箱"]');
    await page.getByPlaceholder(/邮箱|账号/i).fill(email);
    await page.getByPlaceholder(/密码/i).fill("TestPass123");
    await page.getByRole("button", { name: /登录/i }).click();
    await page.waitForURL(/\/dashboard|\/$/);
  });
});
