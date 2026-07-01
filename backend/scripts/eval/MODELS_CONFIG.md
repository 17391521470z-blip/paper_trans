# 模型配置说明

本目录下的 `models.json` 用于评测，**不会进入业务代码或版本控制**。你可以把真实 API key 写在里面，但请确保不要提交到 Git。

## 从 example 复制

```bash
cd paper-translate/backend
cp scripts/eval/models.example.json scripts/eval/models.json
```

## 配置字段

```json
{
  "name": "模型别名，用于报告",
  "base_url": "https://api.siliconflow.cn/v1",
  "api_key": "你的 key",
  "model": "硅基流动上的完整模型 ID",
  "prompt_price_cny_per_1k": 0.001,
  "completion_price_cny_per_1k": 0.002
}
```

## 当前 5 个模型配置

| name | model | 备注 |
|---|---|---|
| deepseek-v4-flash-silicon | `deepseek-ai/DeepSeek-V4-Flash` | 便宜、快 |
| deepseek-v4-pro-silicon | `deepseek-ai/DeepSeek-V4-Pro` | 质量更高、更贵 |
| glm-4.5-air-silicon | `zai-org/GLM-4.5-Air` | 智谱轻量版 |
| qwen-3.5-silicon | `Qwen/Qwen3.5-397B-A17B` | 通义千问 MoE |
| qwen-3.6-silicon | `Qwen/Qwen3.6-35B-A3B` | 通义千问 MoE |

## 价格说明

`models.example.json` 中的价格为**估算值**，基于网络公开信息换算。实际价格请以 [硅基流动官方定价](https://siliconflow.cn/pricing) 为准。

建议运行前登录控制台，按每个模型当前价格更新 `prompt_price_cny_per_1k` 和 `completion_price_cny_per_1k`。如果价格填 0，报告中的成本列也会是 0，但 token 消耗仍会记录。

## 运行

```bash
cd paper-translate/backend
python scripts/eval/benchmark.py --models scripts/eval/models.json
```

只跑其中两个：

```bash
python scripts/eval/benchmark.py --model-names deepseek-v4-flash-silicon,glm-4.5-air-silicon
```

## 安全提醒

- `models.json` 已在项目 `.gitignore` 中忽略（如未忽略请手动添加）。
- 不要把含真实 key 的 `models.json` 截图或复制到聊天里。
- 评测脚本不会上传或发送 key 到任何第三方，仅在本地调用硅基流动 API。
