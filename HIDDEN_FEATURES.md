# Hidden Features — 暂时禁用的功能

本文档记录项目当前**已实现但暂时对用户隐藏**的功能,以及恢复启用时需要做的事情。

## 1. Markdown 导出 (`format=markdown`)

### 现状

- 代码完整实现,可生成 `.md` 文件
- 用户层面**不可见**:UI 上显示为"敬请期待"灰色禁用按钮,后端 API 返回 `410 Gone`
- 实际从未对用户生成过(worker 不再调用 `convert_pdf_to_markdown`)

### 为什么不直接打开

转换基于 `pdfplumber` + `pypandoc` 从翻译后的 PDF 反向提取,质量不可接受:

| 问题 | 根因 |
|---|---|
| 双语段落错乱 | dual PDF 左右栏布局,文字流被打散 |
| 公式全丢 | 公式在 PDF 里是矢量或图片,提取器拿不到 LaTeX |
| 表格变文本流 | 行列结构信息在提取层就丢了 |
| 章节识别错误 | 没接 Section model,只能按页切 |
| 参考文献被翻译 | skip_references 标识没传给 markdown 提取层 |

要让 Markdown "基本可用" 需要至少 **0.5 人天** 改写提取逻辑,而"格式大部分正确"需要 1-2 周接 babeldoc 结构化输出层。

## 2. Word 文档导出 (`format=docx`)

### 现状

- 代码完整实现,通过 `pypandoc` 把 PDF 转 `.docx`
- UI 灰色禁用,后端 API 返回 `410 Gone`

### 为什么不直接打开

`pypandoc --from pdf --to docx` 走的还是文本提取路径,所有 markdown 的问题 docx 一样有,且**额外多**:

- Word 的样式/段落样式无法从 PDF 反推,生成的文件全是"正文 Normal"
- 图丢失或被错位嵌入
- 表格跨页会被错误合并

要"可用"也要走结构化识别,工时同 Markdown。

---

## 恢复启用步骤

### 后端 (3 个文件 + 1 个 .env)

**Step 1**: 编辑 `backend/.env`

```bash
ENABLE_MARKDOWN_EXPORT=true
ENABLE_DOCX_EXPORT=true
```

**Step 2**: 不需要改代码 — `backend/app/core/config.py` 已经读取这两个变量,`backend/app/workers/tasks.py` 的 worker 会自动重新调用 `convert_pdf_to_markdown` 和 `convert_pdf_to_docx`。

**Step 3**: 重启 worker(`uvicorn` / Dramatiq)。

### 前端 (3 个文件)

**Step 1**: `frontend/src/components/download/DownloadMenu.tsx`
- 把 `FORMAT_OPTIONS` 里 `markdown` 和 `docx` 两项的 `disabled: true` 删掉
- 把 `hint` 改回业务文案:"适合笔记软件" / "可继续编辑"

**Step 2**: `frontend/src/pages/TranslatePage.tsx`
- 两个 `<DownloadLink>` 的 `disabled` 和 `comingSoonHint` 属性删掉

**Step 3**: `frontend/src/pages/{HomePage,BillingPage,LoginPage}.tsx` 与 `lib/constants.ts` / `components/landing/PricingTable.tsx`
- 把"双 / 单语 PDF"文案改回"双语文档 + Markdown 导出"

### 验证清单

启用后跑下面 5 项确认没有回归:

```bash
# 1. 后端启动日志看到 markdown/document 步骤的 progress
curl -X POST http://localhost:8000/api/v1/tasks -H "Authorization: Bearer $TOKEN" -F "file=@test.pdf"
# 观察 worker log: 应出现 "markdown generated" 和 "docx generated"

# 2. 下载端点返回真实文件
curl -o translated.md "http://localhost:8000/api/v1/tasks/$TASK_ID/download?format=markdown" -H "Authorization: Bearer $TOKEN"
head translated.md  # 应是 markdown 文本而非 HTML 错误页

# 3. 前端 UI 看到"可点击"的 Markdown / Word 按钮
# 浏览器打开 /dashboard,点击下载按钮,菜单里 Markdown / Word 不是灰色的

# 4. 检查 README/营销文案没有误导
grep -i markdown README.md  # 不应再出现"已禁用"的字样

# 5. 翻译工作台 4 个按钮都能点击
浏览器 /translate,翻译完成后,4 个 DownloadLink 都能点
```

---

## 受影响的文件清单

| 文件 | 改动 |
|---|---|
| `backend/app/core/config.py` | 新增 `enable_markdown_export` / `enable_docx_export` 开关 |
| `backend/app/workers/tasks.py` | worker 调用 `convert_pdf_to_markdown` / `convert_pdf_to_docx` 包了一层 `if settings.enable_*_export:` |
| `backend/app/api/v1/tasks.py` | 下载端点 `format=md/docx` 返回 410 + `feature_disabled` 错误码 |
| `backend/.env.example` | 文档化两个开关 |
| `frontend/src/components/download/DownloadMenu.tsx` | 菜单中 md/docx 选项标 `disabled: true` + "敬请期待"徽标 |
| `frontend/src/pages/TranslatePage.tsx` | `DownloadLink` 加 `disabled` prop,两个按钮传 `disabled comingSoonHint` |
| `frontend/src/lib/constants.ts` | 套餐文案 |
| `frontend/src/components/landing/PricingTable.tsx` | 套餐对比文案 |
| `frontend/src/pages/HomePage.tsx` | 首页卖点文案 |
| `frontend/src/pages/BillingPage.tsx` | 订阅页说明 |
| `frontend/src/pages/LoginPage.tsx` | 登录页特性列表 |

## 没改的文件 (保留完整代码,只是不执行)

- `backend/app/services/markdown_service.py` — `convert_pdf_to_markdown` / `convert_pdf_to_docx` 完整保留,启用时立即可用
- `backend/app/models/task.py` — Task 模型保留 `result_md_url` / `result_docx_url` 字段(数据库 schema 没改)
- `backend/app/schemas/task.py` — Pydantic schema 保留字段
- `frontend/src/stores/taskStore.ts` — `TaskInfo` 保留 `result_md_url` / `result_docx_url`
- `frontend/src/lib/ws.ts` — WS event 字段保留

这些"灰色"代码是有意保留的,不是技术债。`HIDDEN-FEATURE` 注释会在 IDE 里被高亮,便于以后定位。

## 复盘

启用前先回答:

1. **质量底线是什么?** "用户能用" vs "用户满意" 标准不同
2. **目标用户是谁?** 笔记党(Markdown 强需求) vs 阅读党(只要 PDF)
3. **预算多少?** 0.5 天快修 vs 1-2 周 babeldoc 接入 vs 调用第三方 API

如果决定长期不做,建议把 `markdown_service.py` / `result_md_url` / `result_docx_url` 字段从代码里彻底删掉,避免半年后没人记得为什么留着。

如果决定近期做,先做 Markdown(用户呼声高),再做 docx。

## 相关决策记录

- 决定日期:2026-06-28
- 决策人:项目 owner
- 影响范围:所有用户、所有付费档、所有渠道营销文案
- 复盘时间:启用后 30 天