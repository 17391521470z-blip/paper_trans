# 论文翻译模型评测方案

## 1. 目标

在 controlled benchmark + 线上 A/B 两个层面，比较候选 LLM 在 PDF 论文翻译任务上的：

- **成本**：每页 / 每 1000 token 实际花费
- **速度**：首 token 延迟、整页耗时、端到端任务耗时
- **质量**：术语一致性、公式/编号保留、流畅度、漏译/误译

为最终保留单一默认模型、或按质量/速度分层暴露给用户提供数据依据。

## 2. 核心原则

1. **PDF 解析层固定**：所有模型用同一套 `pdf_blocks.extract_blocks()` 输出作为输入，避免 pdf2zh_next 解析差异干扰翻译质量。
2. **Prompt 固定**：统一 system prompt + 术语库片段。
3. **分段策略固定**：统一按段落/标题切块，避免模型上下文长度不同导致输入差异。
4. **质量评估先自动、后人工**：自动指标快速排序，人工盲审决定可用性。
5. **线上 A/B 不暴露模型名**：若后续开放选择，用"标准/高质量/极速"映射模型，而非直接暴露模型名。

## 3. 评测样本

| 维度 | 要求 | 数量 |
|---|---|---|
| 学科 | CS/AI、生物医学、数学/物理、社科、工程 | 每学科 2–3 篇 |
| 长度 | 短（1–3 页）、中（5–10 页）、长（20–50 页） | 每档 3–5 篇 |
| 结构 | 单栏、双栏、含公式/表格、含图表标注、扫描版 | 各至少 1 篇 |
| 语言 | 英文为主，可加入少量德/法/日等小语种测试 | 按需 |

> 建议总样本 20–30 篇，覆盖常见论文形态即可。不要追求大样本，先跑出稳定结论。

## 4. 输入准备

使用 `backend/app/services/pdf_blocks.py` 的 `extract_blocks()` 抽取每个 PDF 的块结构，然后过滤并拼接成翻译单元：

```python
translatable_blocks = [
    b for b in blocks
    if b.type in {"title", "paragraph", "table_caption", "figure_caption"}
]
```

每个 block 视为一个翻译单元。这样：

- 标题和正文分开翻译，避免标题被正文稀释；
- 表格/图片 caption 会被翻译，正文中的表格占位符不会被破坏；
- 公式块单独保留，不参与 LLM 翻译（减少 hallucination）。

## 5. 候选模型

| service | 当前配置模型 | 备注 |
|---|---|---|
| deepseek | deepseek-chat | 当前默认，baseline |
| glm | glm-4-flash | 便宜、快 |
| openai | gpt-4o-mini | OpenAI 兼容、质量可能更稳 |

后续可扩展：deepseek-v4、glm-4-air、gpt-4o 等。

## 6. 测量指标

### 6.1 成本

- 单次调用 cost_cny（来自 `TranslationResult.cost_cny`）
- 每页成本 = 该页所有 block 翻译成本之和 / 页数
- 每千字成本 = 总成本 / 中文字符数

### 6.2 速度

- 首 token 延迟：从请求发出到收到第一个 token 的时间
- Block 翻译耗时：单个 block 翻译总耗时
- 每页耗时：该页所有 block 翻译耗时之和（可并行则记录 wall-clock）
- 端到端耗时：上传 → 结果可下载

### 6.3 质量

| 指标 | 方法 | 权重 |
|---|---|---|
| 自动翻译质量 | COMET / BLEU（需参考译文） | 参考 |
| 术语一致性 | 命中术语库中的 term 是否按指定译文翻译 | 高 |
| 公式/编号保留 | 统计 `(1)`、`Fig. 1`、`Table 2` 等是否原样保留 | 高 |
| 漏译/误译 | 人工抽检 1–5 分 | 高 |
| 流畅度 | 人工抽检 1–5 分 | 中 |

> COMET 需要参考译文。如果样本没有现成参考译文，可以先用默认 DeepSeek-V3 跑一次作为伪参考，再比较其他模型相对得分；或跳过 COMET，只做术语/编号/人工评分。

## 7. 可控 Benchmark 流程

```text
1. 准备 PDF 样本集 → data/benchmark/papers/
2. 对每个 PDF 运行 pdf_blocks.extract_blocks() 得到 blocks.json
3. 对每个模型：
   a. 按统一 prompt 翻译每个 block
   b. 记录 cost、latency、tokens
   c. 输出 translations.json
4. 运行评估脚本：
   a. 术语一致性检查
   b. 公式/编号保留检查
   c. COMET/BLEU（如有参考译文）
5. 生成 benchmark_report.html / .csv
6. 人工盲审评分
```

## 8. 线上 A/B 测试

在 controlled benchmark 有初步结论后，再在小流量用户上验证。

### 8.1 分组策略

- 随机把用户按 `user_id % 100` 分成 N 组
- 每组固定使用一个模型
- 同一用户会话内保持模型一致

### 8.2 后端接入点

当前 `llm_service` 字段已落库（`Task.llm_service`），A/B 只需在 `task_service.enqueue_translation_task()` 或 `tasks.create_task()` 里根据分组覆盖 `llm_service` 即可：

```python
llm_service = resolve_ab_test_model(user.id)  # 返回 deepseek/glm/openai
```

### 8.3 收集指标

- 任务成功率、平均耗时、成本
- 用户是否重新翻译/编辑结果（目前产品无编辑功能，可用"重新上传同一文件"近似）
- 客诉/反馈中提及"翻译质量"的比例
- 付费转化率（若 A/B 周期跨付费漏斗）

### 8.4 最小样本量

- 每组至少 200–500 次完整翻译任务，才能 detect 5% 级别的质量差异
- 若只比较成本和速度，100+ 次即可

## 9. 目录结构

```
backend/scripts/eval/
├── README.md                    # 本方案
├── benchmark.py                 # 主入口：跑 benchmark
├── ab_test_resolver.py          # 线上 A/B 模型分配
├── eval/
│   ├── __init__.py
│   ├── dataset.py               # 加载样本、解析 blocks
│   ├── models.py                # 统一调用多模型
│   ├── metrics.py               # 术语/编号/COMET 评分
│   └── report.py                # 输出报告
├── data/
│   ├── papers/                  # 原始 PDF
│   ├── blocks/                  # 解析后的 blocks.json
│   ├── translations/            # 各模型翻译结果
│   └── reports/                 # 评测报告
└── prompts/
    └── translate_system.txt     # 统一 system prompt
```

## 10. 后续决策规则

| 场景 | 建议 |
|---|---|
| DeepSeek-V3 质量显著优于其他，且成本可控 | 保持单一默认模型，不开放选择 |
| GLM-4-Flash 质量接近 DeepSeek，但成本/速度优势明显 | 考虑作为"极速"选项暴露，按不同配额扣减 |
| GPT-4o-mini 在特定学科明显更好 | 可作为"高质量"选项，加价或限制使用 |
| 三者差异不大 | 按成本最低选择默认，保留其他作为灾备 |

## 11. 注意事项

- 评测时关闭 `skip_references` 和 `detect_sections`，直接翻译全部 blocks，避免章节识别引入额外变量。
- 不要在生产环境直接跑大规模 benchmark，应在本地或 staging 跑。
- A/B 测试期间要实时监控成本，防止贵模型组把日成本打爆。
- 记录每次实验的 prompt、模型版本、样本列表，保证可复现。
