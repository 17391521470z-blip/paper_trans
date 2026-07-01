import type { LucideIcon } from 'lucide-react';
import { Sparkles, Wrench, ShieldCheck } from 'lucide-react';

export type ChangelogKind = 'feature' | 'fix' | 'security';

export interface ChangelogEntry {
  /** ISO 日期字符串,如 2026-06-28 */
  date: string;
  /** 简短标题,1 行 */
  title: string;
  /** 1-2 句描述 */
  description: string;
  /** 分类 */
  kind: ChangelogKind;
  /** 可选版本号 */
  version?: string;
}

export const KIND_META: Record<
  ChangelogKind,
  { label: string; tone: string; Icon: LucideIcon }
> = {
  feature: {
    label: '新功能',
    tone: 'bg-brand-50 text-brand-700',
    Icon: Sparkles,
  },
  fix: {
    label: '修复',
    tone: 'bg-amber-50 text-amber-700',
    Icon: Wrench,
  },
  security: {
    label: '安全',
    tone: 'bg-emerald-50 text-emerald-700',
    Icon: ShieldCheck,
  },
};

/**
 * 按 date 倒序排列;同一天最新条目放最上。
 * 修改这里即可同时驱动侧栏"最近 6 条"和独立 /changelog 全量列表。
 */
export const CHANGELOG_ENTRIES: ChangelogEntry[] = [
  {
    date: '2026-06-30',
    version: '0.2.1',
    kind: 'fix',
    title: '修复术语库 CSV 导出为空文件',
    description:
      '前端下载按钮此前只生成表头,未调用后端 export 端点;现已修复,下载可获取全部词条。',
  },
  {
    date: '2026-06-30',
    version: '0.2.1',
    kind: 'fix',
    title: '修复术语库 CSV 上传 422 校验失败',
    description:
      '修复后端 fastapi.UploadFile 类比较失败与前端 axios 全局 application/json 覆盖 multipart 两处问题。',
  },
  {
    date: '2026-06-30',
    version: '0.2.1',
    kind: 'feature',
    title: '术语库单库上限提升至 1,000 条',
    description:
      '单个自定义术语库最多支持 1,000 条。',
  },
  {
    date: '2026-06-28',
    version: '0.2.0',
    kind: 'feature',
    title: '隐藏 Markdown / Word 导出',
    description:
      '由于转换质量尚未达标,暂时下线 md/docx 导出,详见 HIDDEN_FEATURES.md;后续版本择机恢复。',
  },
  {
    date: '2026-06-28',
    version: '0.2.0',
    kind: 'fix',
    title: '修复 Personal Center 任务列表分页错乱',
    description:
      'DashboardPage 改用本地 page state,不再被 TranslatePage 的 fetchRecentTasks 覆盖。',
  },
  {
    date: '2026-06-28',
    version: '0.1.9',
    kind: 'fix',
    title: '修复纯译文 PDF 实际下载双语',
    description:
      'Worker 现在分别识别 *.zh.dual.pdf 与 *.zh.mono.pdf 并上传,前端通过 ?type=mono 下载纯译文。',
  },
  {
    date: '2026-06-25',
    version: '0.1.8',
    kind: 'fix',
    title: '修复翻译页 ProgressPanel 状态卡在"翻译中"',
    description:
      'ws.ts 的 classifyEvent 现在正确从后端 status 字段推断事件类型,completed 事件能触发 fetchTask 刷新状态。',
  },
  {
    date: '2026-06-20',
    version: '0.1.7',
    kind: 'feature',
    title: 'Dashboard "重新翻译" 按钮带 task 信息',
    description:
      '点击后跳到 /translate?retranslate=<task_id>,自动预填源/目标语言、翻译服务、术语库。',
  },
  {
    date: '2026-06-15',
    version: '0.1.6',
    kind: 'security',
    title: '订单支付改为签名回调校验',
    description:
      '微信 / 支付宝回调使用 HMAC-SHA256 校验签名,杜绝伪造订单状态。',
  },
  {
    date: '2026-06-10',
    version: '0.1.5',
    kind: 'feature',
    title: '支持双 / 单语 PDF 下载',
    description:
      'Worker 现在分别产出 translated-dual.pdf 与 translated-mono.pdf,前端可在下载菜单中分别下载。',
  },
];