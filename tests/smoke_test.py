"""Smoke test for paper-translate — direct backend login + frontend navigation."""
import sys
import time
import json
import requests
from pathlib import Path

from playwright.sync_api import sync_playwright

FRONTEND = "http://localhost:5173"
BACKEND = "http://localhost:8000"
TEST_USER = {"account": "test@paper.com", "password": "Test123456", "account_type": "email"}
PDF_PATH = Path(__file__).resolve().parent.parent / "backend" / "test_smoke.pdf"
SCREENSHOTS = Path(__file__).resolve().parent / "screenshots"

results: list[dict] = []

def ok(name: str, detail: str = "") -> None:
    results.append({"name": name, "passed": True, "detail": detail})
    print(f"  [PASS] {name}")

def fail(name: str, detail: str = "") -> None:
    results.append({"name": name, "passed": False, "detail": detail})
    print(f"  [FAIL] {name}: {detail}")

def login_via_api() -> str | None:
    """Login via backend API and return access_token."""
    try:
        resp = requests.post(
            f"{BACKEND}/api/v1/auth/login",
            json=TEST_USER,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("access_token")
            print(f"  Login API: 200 OK, token={token[:12]}...")
            return token
        print(f"  Login API: {resp.status_code} {resp.text[:100]}")
        return None
    except Exception as e:
        print(f"  Login API: Error - {e}")
        return None

def main():
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Paper-Translate Smoke Test v2")
    print("=" * 60)

    # ── 1. Backend health ──
    print("\n[1] Backend health")
    try:
        r = requests.get(f"{BACKEND}/api/v1/health", timeout=5)
        if r.status_code == 200 and r.json().get("status") == "ok":
            ok("Backend health", "200 OK")
        else:
            fail("Backend health", f"status={r.status_code}")
    except Exception as e:
        fail("Backend health", str(e)[:100])
        print("Backend not available. Aborting.")
        return

    # ── 2. Login via API ──
    print("\n[2] Login via API")
    token = login_via_api()
    if token:
        ok("Login via API", f"token obtained ({len(token)} chars)")
    else:
        fail("Login via API", "could not obtain token")
        # Try once more after short wait (rate limit)
        time.sleep(60)
        token = login_via_api()
        if token:
            ok("Login via API (retry)", "token obtained")
        else:
            fail("Login via API (retry)", "still failed")
            print("Cannot continue without auth token.")
            return

    # ── 3-10: Browser tests ──
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=r"C:\Users\gugu_zhang\AppData\Local\ms-playwright\chromium-1217\chrome-win64\chrome.exe",
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page_errors: list[str] = []
        def on_page_error(err):
            page_errors.append(err.message)
        page.on("pageerror", on_page_error)

        try:
            # Inject auth token into zustand persist store (key = "pt.auth")
            print("\n[3] Inject auth session")
            page.goto(FRONTEND, wait_until="domcontentloaded", timeout=20000)
            session_data = {
                "state": {
                    "token": token,
                    "user": {
                        "id": "7d0f33fd-233a-4405-a353-611d3efc2e6d",
                        "email": "test@paper.com",
                        "display_name": "Test User",
                    },
                    "isAuthenticated": True,
                },
                "version": 0,
            }
            page.evaluate(f"""localStorage.setItem('pt.auth', JSON.stringify({json.dumps(session_data)}));""")
            page.wait_for_timeout(1000)
            ok("Session injected")

            # ── 4. Navigate to translate ──
            print("\n[4] Translate page after auth")
            page.goto(f"{FRONTEND}/translate", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
            current_url = page.url
            if "/login" in current_url:
                fail("Translate access", f"redirected to login: {current_url}")
            else:
                ok("Translate page accessible", f"url={current_url[:60]}")
            page.screenshot(path=str(SCREENSHOTS / "04_translate_page.png"), full_page=True)

            # ── 5. Upload area visible ──
            print("\n[5] Upload area")
            upload_text = page.locator("text=拖拽 PDF").first
            select_btn = page.locator("button").filter(has_text="选择文件").first
            if upload_text.is_visible() or select_btn.is_visible():
                ok("Upload area visible")
            else:
                fail("Upload area", "not found on translate page")

            # ── 6. Select file ──
            print("\n[6] Select PDF file")
            if select_btn.is_visible():
                with page.expect_file_chooser() as fc_info:
                    select_btn.click()
                file_chooser = fc_info.value
                file_chooser.set_files(str(PDF_PATH))
                page.wait_for_timeout(4000)
                ok("File selected", str(PDF_PATH.name))
            else:
                fail("File select", "button not visible")
            page.screenshot(path=str(SCREENSHOTS / "06_file_selected.png"), full_page=True)

            # ── 7. File label visible ──
            print("\n[7] File label")
            if page.locator("text=test_smoke.pdf").first.is_visible():
                ok("File label visible", "test_smoke.pdf shown")
            else:
                fail("File label", "filename not found on page")

            # ── 8. Page count ──
            print("\n[8] Page count reading")
            reading_text = page.locator("text=正在读取").first
            count_text = page.locator("text=/\\d+ 页/").first
            if reading_text.is_visible():
                ok("Page count reading", "spinner visible")
            elif count_text.is_visible():
                ok("Page count", count_text.inner_text()[:40])
            else:
                page.wait_for_timeout(3000)
                if reading_text.is_visible():
                    ok("Page count reading", "spinner appeared after wait")
                elif count_text.is_visible():
                    ok("Page count", count_text.inner_text()[:40])
                else:
                    fail("Page count", "not detected")

            # ── 9. Start translation button ──
            print("\n[9] Start translation button")
            translate_btn = page.locator("button").filter(has_text="开始翻译").first
            if translate_btn.is_visible():
                translate_btn.click()
                page.wait_for_timeout(5000)
                ok("Translation started", "button clicked")
            else:
                fail("Start translation", "button not visible")
            page.screenshot(path=str(SCREENSHOTS / "09_post_submit.png"), full_page=True)

            # ── 10. JS errors ──
            print("\n[10] JS errors & API alerts")
            alert_els = page.locator('[role="alert"]').all()
            errors = []
            for el in alert_els[:5]:
                try:
                    txt = el.inner_text()
                    if any(kw in txt for kw in ["500", "无法解析", "Internal Server"]):
                        errors.append(txt)
                except:
                    pass
            if errors:
                fail("API errors", "; ".join(errors))
            elif page_errors:
                fail("JS errors", "; ".join(page_errors[:3]))
            else:
                ok("No critical errors", "clean")
        finally:
            browser.close()

    # ── Summary ──
    print("\n" + "=" * 60)
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    print(f"RESULTS: {passed} passed, {failed} failed, {len(results)} total")
    print("=" * 60)
    for r in results:
        icon = "✅" if r["passed"] else "❌"
        detail = f" — {r['detail']}" if r.get("detail") else ""
        print(f"  {icon} {r['name']}{detail}")

    if failed:
        print(f"\nScreenshots saved to: {SCREENSHOTS}")
        sys.exit(1)
    else:
        print(f"\n🎉 All tests passed! Screenshots at: {SCREENSHOTS}")

if __name__ == "__main__":
    main()