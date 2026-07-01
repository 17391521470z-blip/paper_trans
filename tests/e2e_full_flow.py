"""End-to-end full flow: Login → Upload → Translate → Monitor → Verify → Debug.

Captures ALL errors, console messages, API failures and screenshots at every step.
"""
import json
import sys
import time
import requests
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

FRONTEND = "http://localhost:5173"
BACKEND = "http://localhost:8000"
TEST_USER = {"account": "test@paper.com", "password": "Test123456", "account_type": "email"}
PDF_PATH = Path(__file__).resolve().parent.parent / "backend" / "test_smoke.pdf"
REPORT_DIR = Path(__file__).resolve().parent / "reports"
SCREENSHOTS = REPORT_DIR / "screenshots"

REPORT: dict = {"started": datetime.now().isoformat(), "steps": [], "issues": [], "summary": ""}
COLLECTED = {"console": [], "page_errors": [], "api_failures": [], "api_successes": []}


def step(name: str) -> dict:
    s = {"name": name, "status": "pending", "detail": "", "duration_s": 0}
    REPORT["steps"].append(s)
    return s


def pass_step(s: dict, detail: str = "") -> None:
    s["status"] = "pass"; s["detail"] = detail
    print(f"  ✅ {s['name']}" + (f" — {detail}" if detail else ""))


def fail_step(s: dict, detail: str = "") -> None:
    s["status"] = "fail"; s["detail"] = detail
    REPORT["issues"].append(f"[{s['name']}] {detail}")
    print(f"  ❌ {s['name']}: {detail}")


def issue(category: str, detail: str) -> None:
    REPORT["issues"].append(f"[{category}] {detail}")
    print(f"  ⚠️ ISSUE [{category}]: {detail}")


def now_ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def main():
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)

    # Ensure test PDF exists
    if not PDF_PATH.exists():
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(str(PDF_PATH))
        for i in range(3):
            c.drawString(72, 750 - i * 200, f"Page {i+1}: Deep learning has revolutionized NLP.")
            c.showPage()
        c.save()

    print("=" * 70)
    print("E2E Full Flow Test: PDF Upload → Translation → Monitor")
    print("=" * 70)

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: Backend + Login
    # ═══════════════════════════════════════════════════════════
    print("\n── Phase 1: Backend & Authentication ──")

    s1 = step("Backend health")
    try:
        r = requests.get(f"{BACKEND}/api/v1/health", timeout=5)
        r.raise_for_status()
        pass_step(s1, f"200 OK, version={r.json().get('version')}")
    except Exception as e:
        fail_step(s1, str(e)); return

    s2 = step("Login via API")
    try:
        r = requests.post(f"{BACKEND}/api/v1/auth/login", json=TEST_USER, timeout=10)
        if r.status_code == 200:
            data = r.json()
            token = data["access_token"]
            pass_step(s2, f"token={token[:15]}...")
        else:
            fail_step(s2, f"HTTP {r.status_code}: {r.text[:100]}")
            return
    except Exception as e:
        fail_step(s2, str(e)); return

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: Launch Browser + Inject Session
    # ═══════════════════════════════════════════════════════════
    print("\n── Phase 2: Browser & Session ──")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=r"C:\Users\gugu_zhang\AppData\Local\ms-playwright\chromium-1217\chrome-win64\chrome.exe",
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # --- Capture everything ---
        console_msgs: list[str] = []
        def on_console(msg):
            console_msgs.append(f"[{msg.type}] {msg.text[:200]}")
            COLLECTED["console"].append({"type": msg.type, "text": msg.text[:300], "ts": now_ts()})
        page.on("console", on_console)

        page_errors: list[str] = []
        def on_page_err(err):
            page_errors.append(err.message)
            COLLECTED["page_errors"].append({"message": err.message, "ts": now_ts()})
        page.on("pageerror", on_page_err)

        api_events: list[str] = []
        def on_response(resp):
            if "/api/v1/" in resp.url:
                txt = ""
                try:
                    body = resp.text()[:200] if resp.headers.get("content-type", "").startswith("application/json") else "[binary]"
                except:
                    body = "[error reading]"
                evt = f"{resp.status} {resp.request.method} {resp.url.split('/api/v1/')[-1]}"
                api_events.append(evt)
                if resp.status >= 400:
                    COLLECTED["api_failures"].append({"status": resp.status, "url": evt, "body": body, "ts": now_ts()})
                else:
                    COLLECTED["api_successes"].append({"status": resp.status, "url": evt, "ts": now_ts()})
        page.on("response", on_response)

        def screenshot(name: str) -> None:
            path = str(SCREENSHOTS / f"{len(REPORT['steps']):02d}_{name}.png")
            page.screenshot(path=path, full_page=True)

        try:
            # ── S3: Inject session ──
            s3 = step("Inject session")
            page.goto(FRONTEND, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(1500)
            session_data = {
                "state": {
                    "token": token,
                    "user": {"id": "7d0f33fd-233a-4405-a353-611d3efc2e6d", "email": "test@paper.com", "display_name": "Test"},
                    "isAuthenticated": True,
                },
                "version": 0,
            }
            page.evaluate(f"localStorage.setItem('pt.auth', JSON.stringify({json.dumps(session_data)}));")
            page.wait_for_timeout(1000)
            pass_step(s3)
            screenshot("session_injected")

            # ── S4: Navigate to translate ──
            s4 = step("Navigate to /translate")
            page.goto(f"{FRONTEND}/translate", wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)
            current_url = page.url
            if "/login" in current_url:
                fail_step(s4, f"redirected to login: {current_url}")
            else:
                pass_step(s4, f"url={current_url[:60]}")
            screenshot("translate_page")

            # ── S5: Upload area ──
            s5 = step("Upload area visible")
            select_btn = page.locator("button").filter(has_text="选择文件").first
            drop_text = page.locator("text=拖拽 PDF").first
            if select_btn.is_visible() or drop_text.is_visible():
                pass_step(s5)
            else:
                fail_step(s5, "neither button nor text found")
            screenshot("upload_area")

            # ── S6: Select file ──
            s6 = step("Select PDF file")
            if select_btn.is_visible():
                with page.expect_file_chooser() as fc:
                    select_btn.click()
                fc.value.set_files(str(PDF_PATH))
                page.wait_for_timeout(3000)
                pass_step(s6, f"file={PDF_PATH.name}")
            else:
                fail_step(s6, "button not visible")
            screenshot("file_selected")

            # ── S7: File name check ──
            s7 = step("File label shown")
            label = page.locator(f"text={PDF_PATH.name}").first
            if label.is_visible():
                pass_step(s7, PDF_PATH.name)
            else:
                # Check if "正在读取" overlay is shown
                if page.locator("text=正在读取").first.is_visible():
                    issue("file-label", "spinner shown, PDF parsing may be slow")
                    pass_step(s7, "parsing...")
                else:
                    fail_step(s7, "filename not found")
            screenshot("file_label")

            # ═══════════════════════════════════════════════════
            # PHASE 3: Start Translation + Monitor
            # ═══════════════════════════════════════════════════
            print("\n── Phase 3: Translation & Monitoring ──")

            # ── S8: Click Start ──
            s8 = step("Click start translation")
            translate_btn = page.locator("button").filter(has_text="开始翻译").first
            if translate_btn.is_visible() and translate_btn.is_enabled():
                translate_btn.click()
                page.wait_for_timeout(2000)
                pass_step(s8)
            else:
                visible = translate_btn.is_visible()
                enabled = translate_btn.is_enabled()
                fail_step(s8, f"visible={visible} enabled={enabled}")
            screenshot("translation_started")

            # ── S9: Wait for progress ──
            s9 = step("Monitor progress (wait up to 120s)")
            max_wait = 120
            seen_status = set()
            last_screenshot = 0
            for i in range(max_wait):
                page.wait_for_timeout(2000)

                # Check for final status
                status_els = page.locator('[role="alert"], .sonner-toast, .toast').all()
                status_texts = []
                for el in status_els[:10]:
                    try:
                        t = el.inner_text()
                        if t and len(t) > 2:
                            status_texts.append(t[:100])
                    except:
                        pass

                # Check for progress text
                progress_texts = page.locator("text=/pending|processing|completed|failed|error|queued|翻译中/i").all_text_contents()[:5]
                for pt in progress_texts:
                    if pt.strip() and pt.strip() not in seen_status:
                        seen_status.add(pt.strip())
                        print(f"    [{now_ts()}] Status change: {pt.strip()[:80]}")

                # Check API events for task status
                task_events = [e for e in api_events if "/tasks" in e and i > 0]
                if task_events:
                    for te in task_events[-2:]:
                        if te not in seen_status:
                            seen_status.add(te)

                # Take periodic screenshots
                if i - last_screenshot >= 10:
                    screenshot(f"progress_{i:03d}s")
                    last_screenshot = i

                # Check complete/fail
                if any("已完成" in t or "completed" in t.lower() for t in status_texts + list(seen_status)):
                    pass_step(s9, f"completed at ~{i*2}s")
                    screenshot("completed")
                    break
                if any("失败" in t or "出错" in t or "error" in t.lower() for t in status_texts + list(seen_status)):
                    fail_step(s9, f"failed at ~{i*2}s: {'; '.join(status_texts[:3])}")
                    screenshot("failed")
                    break
            else:
                issue("progress", f"still pending after {max_wait}s — showing current state")
                s9["detail"] = f"timeout after {max_wait}s"
                screenshot("timeout")

            # ═══════════════════════════════════════════════════
            # PHASE 4: Diagnostics
            # ═══════════════════════════════════════════════════
            print("\n── Phase 4: Diagnostics ──")

            # ── S10: API errors summary ──
            s10 = step("API error summary")
            failures = COLLECTED["api_failures"]
            if failures:
                urls = set(f["url"] for f in failures)
                fail_step(s10, f"{len(failures)} failures on: {', '.join(list(urls)[:3])}")
            else:
                pass_step(s10, "no API errors")

            # ── S11: Page errors ──
            s11 = step("Page JS errors")
            if page_errors:
                fail_step(s11, f"{len(page_errors)} errors: {page_errors[0][:120]}")
            else:
                pass_step(s11)

            # ── S12: Backend log check ──
            s12 = step("Backend log check (via health)")
            try:
                r = requests.get(f"{BACKEND}/api/v1/health", timeout=5)
                if r.status_code == 200:
                    pass_step(s12, "backend still healthy")
                else:
                    fail_step(s12, f"health returns {r.status_code}")
            except Exception as e:
                fail_step(s12, f"backend unreachable: {e}")

            # ── S13: Task retrieval ──
            s13 = step("Retrieve task via API")
            task_list = []
            try:
                headers = {"Authorization": f"Bearer {token}"}
                r = requests.get(f"{BACKEND}/api/v1/tasks?page_size=5", headers=headers, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    task_list = data.get("items", [])
                    pass_step(s13, f"{len(task_list)} tasks found")
                else:
                    fail_step(s13, f"HTTP {r.status_code}: {r.text[:100]}")
            except Exception as e:
                fail_step(s13, str(e))

            # ── S14: Task detail (latest) ──
            s14 = step("Latest task detail")
            if task_list:
                latest = task_list[0]
                task_id = latest.get("id", "")
                status_str = latest.get("status", "unknown")
                progress = latest.get("progress", 0)
                error_msg = latest.get("error_message", "")
                if error_msg:
                    fail_step(s14, f"status={status_str} progress={progress}% error={error_msg[:100]}")
                    issue("task-error", error_msg[:200])
                else:
                    pass_step(s14, f"status={status_str} progress={progress}%")
            else:
                issue("task-list", "no tasks returned from API")
                s14["detail"] = "no tasks"

            # ── S15: Check task progress ──
            s15 = step("Check task progress value")
            if task_list and task_list[0].get("status") == "pending":
                issue("task-stuck", "Task stuck in pending — Redis/Dramatiq may not be running")
                fail_step(s15, "task stuck at pending")

                # Check env
                from app.core.config import get_settings
                try:
                    import sys
                    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
                    settings = get_settings()
                    print(f"    DEBUG: REDIS_URL={settings.redis_url}")
                    print(f"    DEBUG: upload_tmp_dir={settings.upload_tmp_dir}")
                except Exception as e:
                    print(f"    DEBUG: Could not load settings: {e}")
            else:
                status_str = task_list[0].get("status", "unknown") if task_list else "no-task"
                pass_step(s15, f"status={status_str}")

        finally:
            # Final screenshot
            try:
                screenshot("final_state")
            except Exception:
                pass
            browser.close()

    # ═══════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════
    passed = sum(1 for s in REPORT["steps"] if s["status"] == "pass")
    failed = sum(1 for s in REPORT["steps"] if s["status"] == "fail")
    issues_count = len(REPORT["issues"])
    total = len(REPORT["steps"])

    REPORT["summary"] = f"{passed}/{total} steps passed, {failed} failed, {issues_count} issues found"

    print("\n" + "=" * 70)
    print(f"RESULTS: {REPORT['summary']}")
    print(f"API Success: {len(COLLECTED['api_successes'])} | Failures: {len(COLLECTED['api_failures'])}")
    print(f"Page Errors: {len(COLLECTED['page_errors'])} | Console: {len(COLLECTED['console'])}")
    print("=" * 70)
    for s in REPORT["steps"]:
        icon = {"pass": "✅", "fail": "❌", "pending": "⏳"}.get(s["status"], "?")
        d = f" — {s['detail']}" if s.get("detail") else ""
        print(f"  {icon} {s['name']}{d}")

    if REPORT["issues"]:
        print(f"\n⚠️ ISSUES FOUND ({len(REPORT['issues'])}):")
        for idx, iss in enumerate(REPORT["issues"], 1):
            print(f"  {idx}. {iss}")

    # Save full report
    report_path = REPORT_DIR / "e2e_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_data = {**REPORT, "api_failures": COLLECTED["api_failures"], "page_errors": COLLECTED["page_errors"]}
    report_path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n📄 Full report: {report_path}")
    print(f"📸 Screenshots: {SCREENSHOTS}")

    # Return issues for auto-fix
    return REPORT["issues"]


if __name__ == "__main__":
    issues_found = main()
    if issues_found:
        print(f"\n🔧 Starting auto-fix for {len(issues_found)} issues...")
        sys.exit(1)
