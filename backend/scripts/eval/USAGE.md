# 论文翻译模型评测脚本

## 快速开始

1. 把要评测的 PDF 放入 `backend/scripts/eval/data/papers/`（可带子目录）。
2. （可选）准备术语库 JSON：`backend/scripts/eval/data/terms.json`。
3. 确保后端 `.env` 已配置 `DEEPSEEK_API_KEY`、`GLM_API_KEY`、`OPENAI_API_KEY`。
4. 进入后端虚拟环境，执行：

```bash
cd paper-translate/backend
python scripts/eval/benchmark.py
```

默认会同时评测 deepseek / glm / openai 三个服务。

## 仅跑指定模型

```bash
python scripts/eval/benchmark.py --models deepseek,glm
```

## 使用术语库

```bash
python scripts/eval/benchmark.py --terms scripts/eval/data/terms.json
```

## 输出

- `backend/scripts/eval/data/translations/<paper>_<service>.json`：原始翻译结果
- `backend/scripts/eval/data/reports/benchmark.csv`：CSV 汇总
- `backend/scripts/eval/data/reports/benchmark.html`：HTML 可视化报告

## 线上 A/B 测试

将 `scripts/eval/ab_test_resolver.py` 中的 `AB_TEST_VARIANTS` 和 `ab_test_enabled` 按需调整后，在 `app/services/task_service.py` 的 `enqueue_translation_task` 中调用：

```python
from scripts.eval.ab_test_resolver import resolve_model_for_user

service, model = resolve_model_for_user(str(user.id))
llm_service = service
```

即可按用户 ID 哈希分配模型，保持同一用户始终走同一模型。

## 指标说明

| 指标 | 含义 |
|---|---|
| 总成本 | 该论文全部 translatable blocks 翻译成本之和 |
| 平均块耗时 | 总 latency / 块数 |
| 术语一致率 | 术语库中的 term 在译文中出现指定译文的比率 |
| 公式编号保留率 | `(N)` 形式的编号在译文中保留的比率 |
| 图表引用保留率 | `Fig./Figure/Table/Tbl. N` 在译文中保留的比率 |

## 扩展

- 需要 COMET 分数时安装 `unbabel-comet`。
- 需要首 token 延迟时，在 `eval/models.py` 的 `translate_block` 中 hook 底层 `client.chat`。
