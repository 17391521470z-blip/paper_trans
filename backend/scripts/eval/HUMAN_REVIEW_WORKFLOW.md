# 模型评测到上线 Workflow

## 目标

把 benchmark 自动指标和业务主流程生成的双语 PDF 结合起来，通过人工盲审选出最终默认模型，并给出线上分层/单一模型的决策依据。

---

## 阶段 1：Benchmark 初筛

跑 `benchmark.py` 对候选模型打分，主要关注：

- 每页成本（CNY）
- 每块耗时（ms）
- 术语一致率 / 公式编号保留率 / 图表引用保留率

```bash
cd backend
.venv/Scripts/python.exe scripts/eval/benchmark.py \
  --model-names deepseek-v4-flash-silicon,deepseek-v4-pro-silicon,glm-4.5-air-silicon
```

输出：
- `scripts/eval/data/reports/benchmark.csv`
- `scripts/eval/data/reports/benchmark.html`

**筛选规则**：
- 成本或速度明显超出预算的模型直接排除
- 保留 2–3 个候选进入下一阶段

---

## 阶段 2：业务主流程生成双语 PDF

Benchmark 只翻译文本块，不重新组装 PDF。**人工审稿必须看完整双语 PDF**，因此要走业务主流程。

当前业务流通过 `task.llm_service` 选择服务（`deepseek` / `glm` / `openai`），具体模型由 `.env` 中对应服务的 `*_model` 参数决定。

### 推荐做法

1. 从 `data/papers/` 选 3–5 篇代表性论文
2. 对每篇论文、每个候选模型，生成一份 `translated-dual.pdf`
3. 把同一篇论文的不同模型输出放在同一文件夹，命名区分模型

### 通过前端/API 批量生成

```bash
# 1. 临时修改 .env 中对应服务的模型名，例如：
# DEEPSEEK_MODEL=deepseek-ai/DeepSeek-V4-Flash

# 2. 重启 worker

# 3. 调用 API 创建任务
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@scripts/eval/data/papers/adam.pdf" \
  -F "llm_service=deepseek"

# 4. 等待完成，下载 dual PDF
```

> 若候选模型都在同一 service（如都是 DeepSeek），每次只改 `.env` 里的 `DEEPSEEK_MODEL` 并重启 worker；若跨 service，则通过 `llm_service` 参数切换。

---

## 阶段 3：人工盲审

把同一篇论文的多个模型双语 PDF 并排打开，按以下维度打分（1–5 分）：

| 维度 | 检查点 |
|---|---|
| 术语一致性 | 关键术语/缩写是否全文统一、符合学科习惯 |
| 公式上下文 | 公式前后的中文说明是否自然、是否破坏原意 |
| 图表引用 | `Fig.` / `Table` 编号是否保留、caption 翻译是否准确 |
| 流畅度 | 是否像中文学术写作，无严重翻译腔 |
| 漏译/误译 | 是否有段落未译、专业名词错译 |
| 版面质量 | dual PDF 左右对照是否整齐、换行/分页是否合理 |

**建议**：至少 2 人独立评分，取平均分。

---

## 阶段 4：决策

综合 benchmark 指标和人工评分：

| 场景 | 决策 |
|---|---|
| 某模型成本和人工评分都最优 | 设为唯一默认模型，不开放选择 |
| 质量接近但成本差异大 | 选成本最低的作为默认，其他做灾备 |
| 某模型质量明显更好但更贵 | 可作为"高质量"分层选项，额外扣费 |
| 某模型很快但质量稍差 | 可作为"极速"分层选项，低价策略 |

---

## 阶段 5：线上 A/B 验证

人工结论上线前，用小流量 A/B 验证：

- 按 `user_id % N` 把用户分成 N 组
- 每组固定一个模型/策略
- 同一用户会话内保持模型不变
- 监控指标：
  - 任务成功率、平均成本、平均耗时
  - 用户重复上传率（可近似看做"对结果不满意"）
  - 客诉/反馈中提及"翻译质量"的比例
  - 付费转化率（若跨付费漏斗）

**最小样本**：每组 200–500 次完整翻译任务，运行 1–2 周后做最终切换。

---

## 注意事项

1. **Benchmark 与业务流的模型映射**
   - `benchmark.py` 通过 `models.json` 支持任意 OpenAI-compatible 端点
   - 业务主流程目前只支持 `deepseek` / `glm` / `openai` 三个 service
   - 若 benchmark 中的 SiliconFlow 模型要进入业务流，必须映射到这三个 service 之一，并修改对应 `.env` 模型名

2. **不要在生产环境直接跑 benchmark**

3. **实验可复现**
   - 每次对比记录：PDF 样本列表、prompt 版本、模型版本、评分人
   - 建议把评审结果写入 `scripts/eval/data/reviews/`

4. **禁用功能**
   - Markdown / Word 导出当前处于禁用状态（见 `HIDDEN_FEATURES.md`）
   - 人工评审以双语 PDF 为主
