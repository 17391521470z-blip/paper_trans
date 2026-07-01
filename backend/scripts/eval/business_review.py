#!/usr/bin/env python3
"""临时业务主流程多模型对比脚本。

用法：
    cd paper-translate
    set PAPER_TRANSLATE_TOKEN=your_token
    python backend/scripts/eval/business_review.py --pdf backend/scripts/eval/data/papers/adam.pdf

说明：
    1. 读取 backend/scripts/eval/models.json 中的模型配置
    2. 逐个更新 backend/.env 中的 *_BASE_URL / *_API_KEY / *_MODEL
    3. 提示你重启 worker
    4. 上传同一篇 PDF，轮询任务完成，下载 dual PDF 到 review_pdfs/ 目录

注意：
    - 默认复用 deepseek service 槽位测试 SiliconFlow 等 OpenAI 兼容端点
    - 需要提前登录获取 Bearer Token
    - 每次切换模型后必须重启 worker，否则 .env 变更不会生效
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any


def load_models(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("models", data) if isinstance(data, dict) else data
    return items


def update_env(env_path: Path, updates: dict[str, str]) -> None:
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = text.splitlines(keepends=True)
    new_lines: list[str] = []
    keys_updated: set[str] = set()

    for line in lines:
        for key, value in updates.items():
            if line.startswith(f"{key}="):
                line = f"{key}={value}\n"
                keys_updated.add(key)
                break
        new_lines.append(line)

    for key, value in updates.items():
        if key not in keys_updated:
            new_lines.append(f"{key}={value}\n")

    env_path.write_text("".join(new_lines), encoding="utf-8")


def api_request(
    url: str,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    req = urllib.request.Request(url, method=method, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def upload_pdf(base_url: str, token: str, pdf_path: Path, service: str) -> dict[str, Any]:
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body_parts: list[bytes] = [
        f"--{boundary}".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{pdf_path.name}"'.encode(),
        b"Content-Type: application/pdf",
        b"",
        pdf_path.read_bytes(),
        f"--{boundary}".encode(),
        f'Content-Disposition: form-data; name="llm_service"'.encode(),
        b"",
        service.encode(),
        f"--{boundary}--".encode(),
        b"",
    ]
    data = b"\r\n".join(body_parts)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    return api_request(
        f"{base_url}/api/v1/tasks",
        method="POST",
        data=data,
        headers=headers,
        timeout=120,
    )


def poll_task(base_url: str, token: str, task_id: str, max_wait: int = 1800) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{base_url}/api/v1/tasks/{task_id}"
    for _ in range(max_wait // 5):
        data = api_request(url, headers=headers, timeout=30)
        status = str(data.get("status", "")).lower()
        if status in ("completed", "failed", "cancelled"):
            return data
        time.sleep(5)
    raise RuntimeError(f"polling timeout for task {task_id}")


def download_pdf(base_url: str, token: str, task_id: str, dest: Path) -> None:
    url = f"{base_url}/api/v1/tasks/{task_id}/download?type=dual"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler)
    with opener.open(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def main() -> int:
    parser = argparse.ArgumentParser(description="Business-flow multi-model PDF review")
    parser.add_argument("--pdf", required=True, type=Path, help="要翻译的 PDF 文件路径")
    parser.add_argument(
        "--models",
        default=None,
        type=Path,
        help="models.json 路径（默认：脚本同级目录的 models.json）",
    )
    parser.add_argument("--service", default="deepseek", help="业务 service 槽位")
    parser.add_argument("--base-url", default="http://localhost:8000", help="后端 API 地址")
    parser.add_argument("--token", default="", help="Bearer Token，也可通过 PAPER_TRANSLATE_TOKEN 环境变量传入")
    parser.add_argument(
        "--output-dir",
        default=None,
        type=Path,
        help="输出目录（默认：scripts/eval/data/review_pdfs/）",
    )
    parser.add_argument(
        "--model-names",
        default=None,
        help="只跑指定模型，逗号分隔，例如 deepseek-v4-flash-silicon,glm-4.5-air-silicon",
    )
    args = parser.parse_args()

    token = args.token or os.environ.get("PAPER_TRANSLATE_TOKEN", "")
    if not token:
        print("错误：请提供 --token 或设置 PAPER_TRANSLATE_TOKEN 环境变量")
        return 1

    script_dir = Path(__file__).parent
    repo_root = script_dir.parents[2]  # backend/scripts/eval -> backend -> repo root
    models_path = args.models or script_dir / "models.json"
    env_path = repo_root / "backend" / ".env"
    output_dir = args.output_dir or script_dir / "data" / "review_pdfs"

    if not env_path.exists():
        print(f"错误：找不到 .env: {env_path}")
        return 1
    if not models_path.exists():
        print(f"错误：找不到 models.json: {models_path}")
        return 1
    if not args.pdf.exists():
        print(f"错误：找不到 PDF: {args.pdf}")
        return 1

    models = load_models(models_path)
    if args.model_names:
        wanted = {s.strip() for s in args.model_names.split(",")}
        models = [m for m in models if m.get("name") in wanted]
    if not models:
        print("错误：没有可测试的模型")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    service_upper = args.service.upper()

    print(f"准备测试 {len(models)} 个模型，PDF: {args.pdf}")
    print(f"输出目录: {output_dir}")
    print("注意：每次切换模型后需要手动重启 worker\n")

    for model in models:
        name = model.get("name", "unknown")
        model_id = model.get("model", "")
        print(f"=== [{name}] {model_id} ===")

        updates = {
            f"{service_upper}_BASE_URL": model.get("base_url", ""),
            f"{service_upper}_API_KEY": model.get("api_key", ""),
            f"{service_upper}_MODEL": model_id,
        }
        update_env(env_path, updates)
        print(f"已更新 {env_path}")
        print("请重启 worker 后按 Enter 继续...")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            print("用户中断")
            return 0

        try:
            print("上传 PDF...")
            result = upload_pdf(args.base_url, token, args.pdf, args.service)
            task_id = result.get("task_id")
            if not task_id:
                print(f"创建任务失败: {result}")
                continue
            print(f"任务已创建: {task_id}")

            print("等待翻译完成...")
            task = poll_task(args.base_url, token, task_id)
            if task.get("status") != "completed":
                print(f"任务失败: {task.get('error_message')}")
                continue

            dest = output_dir / f"{args.pdf.stem}_{name}.pdf"
            print(f"下载双语 PDF -> {dest}")
            download_pdf(args.base_url, token, task_id, dest)
            print(f"完成: {dest}\n")
        except Exception as exc:  # noqa: BLE001
            print(f"[{name}] 出错: {exc}\n")
            continue

    print("全部测试完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
