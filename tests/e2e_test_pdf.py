"""End-to-end test using test.pdf from project root.

Flow:
  1. Backend health check
  2. Login via API to obtain JWT
  3. Upload test.pdf via API (multipart/form-data)
  4. Poll task progress via REST
  5. Verify completion status
  6. Download translated PDF (follow 302 redirect to signed URL)
  7. Verify downloaded file is a valid PDF
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Allow override via env (e.g., for paths with non-ASCII chars on Windows console)
PDF_PATH = Path(os.environ.get("TEST_PDF_PATH", PROJECT_ROOT / "test.pdf"))
BACKEND = os.environ.get("TEST_BACKEND_URL", "http://127.0.0.1:8000")
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


def http_request(url: str, method: str = "GET", *, headers: dict | None = None,
                 data: bytes | None = None, timeout: int = 30) -> tuple[int, bytes, dict]:
    req = urllib.request.Request(url, method=method, headers=headers or {}, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def main() -> int:
    print("=" * 70)
    print(" PDF Translation E2E (test.pdf from project root)")
    print("=" * 70)

    if not PDF_PATH.is_file():
        print(f"FATAL: test.pdf not found at {PDF_PATH}")
        return 1
    pdf_size = PDF_PATH.stat().st_size
    print(f"PDF: {PDF_PATH.name} ({pdf_size:,} bytes)")
    print()

    # ── 1. Backend health ──
    s1 = step("Backend health")
    status, body, _ = http_request(f"{BACKEND}/api/v1/health")
    if status == 200:
        pass_step(s1, json.loads(body))
    else:
        fail_step(s1, f"status={status} body={body[:200]!r}")
        return 1

    # ── 2. Login ──
    s2 = step("Login via API")
    status, body, _ = http_request(
        f"{BACKEND}/api/v1/auth/login",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(TEST_USER).encode(),
    )
    if status != 200:
        fail_step(s2, f"login failed status={status} body={body[:300]!r}")
        return 1
    login_data = json.loads(body)
    token = login_data.get("access_token")
    if not token:
        fail_step(s2, "no access_token in response")
        return 1
    pass_step(s2, f"token={token[:24]}...")
    auth = {"Authorization": f"Bearer {token}"}

    # ── 3. Upload test.pdf ──
    s3 = step(f"Upload test.pdf ({pdf_size:,} bytes)")
    boundary = "----pt-test-boundary"
    body_parts = []
    for name, value in [
        ("source_language", "en"),
        ("target_language", "zh"),
        ("llm_service", "deepseek"),
        ("skip_references", "true"),
        ("detect_sections", "true"),
        ("output_formats", "pdf"),
    ]:
        body_parts.append(f"--{boundary}\r\n")
        body_parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n')
        body_parts.append(f"{value}\r\n")
    body_parts.append(f"--{boundary}\r\n")
    body_parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{PDF_PATH.name}"\r\n'
    )
    body_parts.append("Content-Type: application/pdf\r\n\r\n")
    pdf_bytes = PDF_PATH.read_bytes()
    body_parts_binary = "".join(body_parts).encode() + pdf_bytes + f"\r\n--{boundary}--\r\n".encode()

    status, body, _ = http_request(
        f"{BACKEND}/api/v1/tasks",
        method="POST",
        headers={**auth, "Content-Type": f"multipart/form-data; boundary={boundary}"},
        data=body_parts_binary,
        timeout=120,
    )
    if status != 201:
        fail_step(s3, f"upload failed status={status} body={body[:500]!r}")
        return 1
    upload_data = json.loads(body)
    task_id = upload_data.get("task_id")
    if not task_id:
        fail_step(s3, f"no task_id in response: {upload_data}")
        return 1
    if upload_data.get("cached"):
        pass_step(s3, f"cached task_id={task_id} status={upload_data.get('status')}")
        # Skip to download
        return _download_and_verify(token, task_id)
    pass_step(s3, f"task_id={task_id} status={upload_data.get('status')}")

    # ── 4. Poll task progress ──
    s4 = step("Poll task until completed/failed (max 360s)")
    start = time.time()
    max_wait = 360
    final = None
    while time.time() - start < max_wait:
        status, body, _ = http_request(
            f"{BACKEND}/api/v1/tasks/{task_id}",
            headers=auth,
        )
        if status != 200:
            time.sleep(2)
            continue
        info = json.loads(body)
        t_status = info.get("status")
        progress = info.get("progress", 0)
        elapsed = int(time.time() - start)
        print(f"    [{elapsed:3d}s] status={t_status} progress={progress}%")
        if t_status == "completed":
            final = info
            pass_step(s4, f"completed in {elapsed}s progress={progress}%")
            break
        if t_status == "failed":
            fail_step(s4, f"task failed: {info.get('error_message')}")
            return 1
        if t_status == "cached":
            final = info
            pass_step(s4, f"cached task in {elapsed}s")
            break
        time.sleep(4)

    if final is None:
        fail_step(s4, f"timed out after {max_wait}s")
        return 1

    return _download_and_verify(token, task_id)


def _download_and_verify(token: str, task_id: str) -> int:
    """Download translated PDF and verify."""
    auth = {"Authorization": f"Bearer {token}"}
    downloads_dir = PROJECT_ROOT / "tests" / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    # ── 5. Download PDF ──
    s5 = step("Download translated PDF")
    status, body, headers = http_request(
        f"{BACKEND}/api/v1/tasks/{task_id}/download?format=pdf",
        headers=auth,
    )
    if status != 200:
        fail_step(s5, f"download failed status={status} body={body[:300]!r}")
        return 1
    target = downloads_dir / f"translated_{task_id[:8]}.pdf"
    target.write_bytes(body)
    size = target.stat().st_size
    header = target.read_bytes()[:5]
    is_pdf = header.startswith(b"%PDF-")
    if not is_pdf:
        fail_step(s5, f"file is not PDF (header={header!r}, size={size})")
        return 1
    pass_step(s5, f"saved={target.name} size={size:,}B is_pdf=True")

    # ── 6. Verify task result_url works ──
    s6 = step("Verify task result_url accessible")
    status, body, _ = http_request(
        f"{BACKEND}/api/v1/tasks/{task_id}",
        headers=auth,
    )
    info = json.loads(body)
    result_url = info.get("result_url", "")
    if not result_url:
        fail_step(s6, "no result_url in task detail")
    else:
        # result_url is relative (e.g., /api/v1/storage/local/...)
        full_url = result_url if result_url.startswith("http") else f"{BACKEND}{result_url}"
        status, body, _ = http_request(full_url)
        if status == 200:
            pass_step(s6, f"result_url OK ({len(body):,}B)")
        else:
            fail_step(s6, f"result_url status={status}")

    # ── Summary ──
    print("\n" + "=" * 70)
    passed = sum(1 for s in REPORT["steps"] if s["status"] == "pass")
    failed = sum(1 for s in REPORT["steps"] if s["status"] == "fail")
    print(f" RESULTS: {passed} passed, {failed} failed, {len(REPORT['steps'])} total")
    print("=" * 70)
    for s in REPORT["steps"]:
        icon = {"pass": "✓", "fail": "✗", "pending": "·"}.get(s["status"], "?")
        print(f"  {icon} {s['name']}" + (f" — {s['detail']}" if s.get('detail') else ""))

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())