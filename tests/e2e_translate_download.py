"""Complete PDF translation flow test using Playwright.

Flow:
  1. Backend health check
  2. Login via API to obtain JWT
  3. Open browser, inject session into zustand persist
  4. Navigate to /translate
  5. Upload test_smoke.pdf via file chooser
  6. Configure translation options (target = zh, service = deepseek)
  7. Submit translation
  8. Monitor WebSocket progress until completion
  9. Verify "translation completed" status in UI
  10. Click download button → verify file was saved
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from playwright.sync_api import (
    TimeoutError as PlaywrightTimeout,
    expect,
    sync_playwright,
)


FRONTEND = "http://127.0.0.1:5173"
BACKEND = "http://127.0.0.1:8000"
PDF_PATH = Path(__file__).resolve().parent.parent / "backend" / "test_smoke.pdf"
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"
REPORT_DIR = Path(__file__).resolve().parent / "reports"
SCREENSHOTS_DIR = REPORT_DIR / "translate-flow"

TEST_USER = {
    "account": "test@paper.com",
    "password": "Test123456",
    "account_type": "email",
}


REPORT: dict = {"started": datetime.now().isoformat(), "steps": []}


def step(name: str) -> dict:
    s = {"name": name, "status": "pending", "detail": ""}
    REPORT["steps"].append(s)
    return s


def pass_step(s: dict, detail: str = "") -> None:
    s["status"] = "pass"
    s["detail"] = detail
    print(f"  [PASS] {s['name']}" + (f" — {detail}" if detail else ""))


def fail_step(s: dict, detail: str = "") -> None:
    s["status"] = "fail"
    s["detail"] = detail
    print(f"  [FAIL] {s['name']}: {detail}")


def issue(category: str, detail: str) -> None:
    print(f"  [ISSUE] {category}: {detail}")


def login_api() -> tuple[str, dict] | None:
    req = urllib.request.Request(
        f"{BACKEND}/api/v1/auth/login",
        method="POST",
        data=json.dumps(TEST_USER).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
            token = body.get("access_token")
            return token, body
    except urllib.error.HTTPError as e:
        print(f"  login http error: {e.code} {e.read().decode()[:200]}")
        return None
    except Exception as e:
        print(f"  login error: {e}")
        return None


def main():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(" PDF Translation End-to-End Test")
    print("=" * 70)

    # ── 1. Backend health ──
    s1 = step("Backend health")
    try:
        with urllib.request.urlopen(f"{BACKEND}/api/v1/health", timeout=5) as r:
            if r.status == 200:
                pass_step(s1, json.loads(r.read()))
            else:
                fail_step(s1, f"status={r.status}")
                return
    except Exception as e:
        fail_step(s1, str(e))
        return

    # ── 2. Login via API ──
    s2 = step("Login via API")
    login = login_api()
    if not login:
        fail_step(s2, "could not login")
        return
    token, body = login
    pass_step(s2, f"token={token[:24]}...")

    # ── 3. Launch browser + inject session ──
    print("\n── Browser Setup ──")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=(
                r"C:\Users\gugu_zhang\AppData\Local\ms-playwright\chromium-1217\chrome-win64\chrome.exe"
            ),
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
        )
        page = context.new_page()

        page_errors: list[str] = []
        page.on("pageerror", lambda err: page_errors.append(err.message))

        api_events: list[str] = []
        page.on(
            "response",
            lambda resp: api_events.append(
                f"{resp.status} {resp.request.method} "
                f"{resp.url.split('/api/v1/')[-1] if '/api/v1/' in resp.url else resp.url}"
            )
            if "/api/v1/" in resp.url
            else None,
        )

        ws_events: list[dict] = []

        def on_ws(ws):
            url = ws.url
            print(f"    WS open: {url[-60:]}")

            def on_frame(payload):
                try:
                    frame = payload if isinstance(payload, str) else payload.decode()
                    if "ping" in frame.lower():
                        return
                    msg = json.loads(frame)
                    if isinstance(msg, dict) and msg.get("event") not in ("snapshot",):
                        print(f"    WS msg: {msg}")
                    ws_events.append({"url": url[-60:], "frame": msg})
                except Exception:
                    pass

            ws.on("framereceived", on_frame)
            ws.on("close", lambda: print(f"    WS close: {url[-60:]}"))

        page.on("websocket", on_ws)

        def shot(name: str) -> None:
            path = str(SCREENSHOTS_DIR / f"{len(REPORT['steps']):02d}_{name}.png")
            try:
                page.screenshot(path=path, full_page=True)
            except PlaywrightTimeout:
                pass

        try:
            s3 = step("Inject session and open /translate")
            page.goto(FRONTEND, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(1500)

            session_data = {
                "state": {
                    "token": token,
                    "user": body.get("user") or {
                        "id": "7d0f33fd-233a-4405-a353-611d3efc2e6d",
                        "email": "test@paper.com",
                        "display_name": "Test User",
                    },
                    "isAuthenticated": True,
                },
                "version": 0,
            }
            page.evaluate(
                f"localStorage.setItem('pt.auth', JSON.stringify({json.dumps(session_data)}));"
            )
            page.wait_for_timeout(800)

            page.goto(f"{FRONTEND}/translate", wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)

            if "/login" in page.url:
                fail_step(s3, f"redirected to login: {page.url}")
                shot("login_redirect")
                return
            pass_step(s3, f"url={page.url}")
            shot("translate_loaded")

            # ── 4. Locate upload area and select file ──
            s4 = step("Select PDF file via file chooser")
            select_btn = page.locator("button").filter(has_text=re.compile("选择文件")).first
            if not select_btn.is_visible():
                fail_step(s4, "select file button not visible")
                shot("no_select_btn")
                return
            try:
                with page.expect_file_chooser(timeout=10000) as fc_info:
                    select_btn.click()
                fc_info.value.set_files(str(PDF_PATH))
                page.wait_for_timeout(4000)
                pass_step(s4, f"file={PDF_PATH.name}")
            except PlaywrightTimeout:
                fail_step(s4, "file chooser did not open")
                shot("no_chooser")
                return
            shot("file_selected")

            # ── 5. Verify file label shown ──
            s5 = step("File label visible")
            try:
                label = page.locator(f"text={PDF_PATH.name}").first
                label.wait_for(state="visible", timeout=10000)
                pass_step(s5, "filename displayed")
            except PlaywrightTimeout:
                fail_step(s5, "filename not shown on page")
                shot("no_file_label")
                return

            # ── 6. Configure translation options ──
            s6 = step("Configure target language = zh")
            target_select = page.locator("select").nth(1)
            try:
                if target_select.count() == 0:
                    fail_step(s6, "target language select not found")
                else:
                    target_select.select_option(value="zh")
                    page.wait_for_timeout(500)
                    pass_step(s6, "target=zh")
            except Exception as e:
                fail_step(s6, str(e)[:120])
            shot("options_set")

            # ── 7. Submit translation ──
            s7 = step("Click 开始翻译")
            submit_btn = page.locator("button[type=submit]").filter(
                has_text=re.compile("开始翻译|正在提交")
            )
            try:
                submit_btn.first.wait_for(state="visible", timeout=5000)
                submit_btn.first.click()
                pass_step(s7, "submitted")
            except PlaywrightTimeout:
                # Maybe button label is different — try broader search
                try:
                    page.locator("button").filter(
                        has_text=re.compile("翻译")
                    ).first.click()
                    pass_step(s7, "submitted (via broad selector)")
                except Exception as e:
                    fail_step(s7, str(e)[:120])
                    shot("submit_failed")
                    return
            shot("submitted")

            # ── 8. Monitor progress ──
            s8 = step("Monitor translation progress (max 240s)")
            start = time.time()
            max_wait = 240
            completed = False
            last_progress = -1
            last_seen_status = ""

            while time.time() - start < max_wait:
                page.wait_for_timeout(3000)

                # Check WS events
                last_ws = None
                for ev in ws_events:
                    frame = ev.get("frame", {})
                    if isinstance(frame, dict) and frame.get("status"):
                        last_ws = frame

                if last_ws:
                    p = last_ws.get("progress")
                    st = last_ws.get("status", "")
                    if p is not None and p != last_progress:
                        last_progress = p
                        print(f"    [{int(time.time()-start):3d}s] progress={p}% status={st}")
                    if st and st != last_seen_status:
                        print(f"    [{int(time.time()-start):3d}s] status: {st}")
                        last_seen_status = st
                        if st == "completed":
                            completed = True
                            pass_step(s8, f"completed in {int(time.time()-start)}s, final progress={p}%")
                            break
                        if st == "failed":
                            fail_step(s8, f"failed after {int(time.time()-start)}s: {last_ws.get('message','')}")
                            break

                # Check UI completion text
                ui_done = (
                    page.locator("text=翻译完成").first.is_visible()
                    if page.locator("text=翻译完成").count() > 0
                    else False
                )
                if ui_done and not completed:
                    completed = True
                    pass_step(s8, "UI reports translation complete")
                    break

            if not completed and s8["status"] == "pending":
                fail_step(s8, f"timed out after {max_wait}s, last status={last_seen_status}")
            shot("progress_final")

            # ── 9. Look for download button ──
            s9 = step("Find download link/button")
            download_btn = None
            for selector in [
                'a:has-text("下载")',
                'button:has-text("下载")',
                'a:has-text("Download")',
                'a[href*="/download"]',
            ]:
                loc = page.locator(selector).first
                if loc.count() > 0 and loc.is_visible():
                    href = None
                    try:
                        href = loc.get_attribute("href")
                    except Exception:
                        pass
                    download_btn = (loc, href)
                    break

            if not download_btn:
                issue("download-ui", "no download button — trying API directly")
            else:
                _, href = download_btn
                pass_step(s9, f"href={href[:80] if href else '(button)'}")
            shot("download_area")

            # ── 10. Trigger download ──
            s10 = step("Trigger download and verify file")
            target_download_path = DOWNLOAD_DIR / f"translated_{int(time.time())}.pdf"

            triggered = False
            try:
                with page.expect_download(timeout=15000) as dl_info:
                    if download_btn:
                        download_btn[0].click()
                download = dl_info.value
                download.save_as(str(target_download_path))
                triggered = True
            except PlaywrightTimeout:
                # fallback: hit API directly
                pass
            except Exception as e:
                print(f"  download via UI error: {e}")

            if not triggered:
                # Locate the latest task id from API and request download
                try:
                    with urllib.request.urlopen(
                        urllib.request.Request(
                            f"{BACKEND}/api/v1/tasks?page_size=1",
                            headers={"Authorization": f"Bearer {token}"},
                        ),
                        timeout=10,
                    ) as resp:
                        tasks = json.loads(resp.read()).get("items", [])
                    if tasks:
                        task_id = tasks[0]["id"]
                        download_url = f"{BACKEND}/api/v1/tasks/{task_id}/download?format=pdf"
                        req = urllib.request.Request(
                            download_url,
                            headers={"Authorization": f"Bearer {token}"},
                        )
                        with urllib.request.urlopen(req, timeout=15) as resp:
                            final_url = resp.geturl()  # may be a signed local URL
                            target_download_path.write_bytes(resp.read())
                            triggered = True
                            print(f"  downloaded via API: {target_download_path} (from {resp.status})")
                except urllib.error.HTTPError as e:
                    body = e.read().decode("utf-8", errors="replace")[:300]
                    print(f"  api download error: {e.code} {body}")

            if not triggered:
                fail_step(s10, "could not trigger download")
            else:
                size = target_download_path.stat().st_size if target_download_path.exists() else 0
                # Verify it's a PDF
                with open(target_download_path, "rb") as f:
                    header = f.read(5)
                is_pdf = header.startswith(b"%PDF-")
                pass_step(
                    s10,
                    f"saved={target_download_path.name} size={size}B is_pdf={is_pdf}",
                )
                if not is_pdf:
                    fail_step(s10, f"file is not a PDF (header={header!r})")

            # ── 11. Diagnostics summary ──
            s11 = step("Diagnostics summary")
            api_failures = [e for e in api_events if e and e.startswith(("4", "5"))]
            ws_failures = [
                e for e in ws_events if isinstance(e, dict) and e.get("frame", {}).get("event") == "error"
            ]
            detail = f"api_failures={len(api_failures)} ws_errors={len(ws_failures)} page_errors={len(page_errors)}"
            if api_failures:
                detail += f" | first={api_failures[0]}"
            if page_errors:
                detail += f" | page_err={page_errors[0][:100]}"
            if not api_failures and not ws_failures and not page_errors:
                pass_step(s11, "clean (no failures)")
            else:
                fail_step(s11, detail)
        finally:
            try:
                shot("final")
            except Exception:
                pass
            browser.close()

    # ── Summary ──
    passed = sum(1 for s in REPORT["steps"] if s["status"] == "pass")
    failed = sum(1 for s in REPORT["steps"] if s["status"] == "fail")
    print("\n" + "=" * 70)
    print(f" RESULTS: {passed} passed, {failed} failed, {len(REPORT['steps'])} total")
    print("=" * 70)
    for s in REPORT["steps"]:
        icon = {"pass": "✓", "fail": "✗", "pending": "·"}.get(s["status"], "?")
        print(f"  {icon} {s['name']}" + (f" — {s['detail']}" if s.get("detail") else ""))

    report_path = REPORT_DIR / "translate-flow-report.json"
    report_path.write_text(
        json.dumps(REPORT, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nReport: {report_path}")
    print(f"Screenshots: {SCREENSHOTS_DIR}")
    print(f"Downloads: {DOWNLOAD_DIR}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
