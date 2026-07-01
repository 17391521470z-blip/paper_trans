import { memo } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  BookOpen,
  FileSpreadsheet,
  FileText,
  GraduationCap,
  Languages,
  PlayCircle,
  Quote,
  ShieldCheck,
  Sigma,
  Sparkles,
} from 'lucide-react';

import { PageTitle } from '../components/seo/PageTitle';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { PricingTable } from '@/components/landing/PricingTable';
import { useAuthStore } from '@/stores/authStore';

const FEATURES = [
  {
    icon: Sigma,
    title: '保留公式与图表',
    description:
      '基于 BabelDOC 与 DocLayout-YOLO，公式、表格、向量图原位保留，仅翻译文字层。',
  },
  {
    icon: BookOpen,
    title: '学术术语库',
    description:
      '内置 CS / AI 200+ 词条，支持上传 CSV 自定义术语，术语一致性自动校验。',
  },
  {
    icon: FileText,
    title: '跳过参考文献',
    description:
      '自动识别 Abstract / Methods / References 等章节结构，DOI 与作者年份原样保留。',
  },
  {
    icon: FileSpreadsheet,
    title: '多格式 PDF 导出',
    description:
      '同时输出双语文档 PDF 与纯译文 PDF，覆盖阅读与二次编辑需求。',
  },
] as const;

const STATS = [
  { label: '日均翻译页数', value: '12,800+' },
  { label: '支持目标语言', value: '9 种' },
  { label: '平均响应时间', value: '< 90s' },
  { label: '注册用户', value: '3,200+' },
] as const;

const TESTIMONIALS = [
  {
    quote:
      '翻译一篇 NeurIPS 论文 30 页，3 分钟拿到双语对照，公式一个都没丢。',
    author: '张同学',
    role: '清华大学 计算机系硕士',
  },
  {
    quote:
      '课题组把 200 多个 ML 术语做成 CSV 上传后，整本综述翻译下来术语零冲突。',
    author: '李教授',
    role: '复旦大学 人工智能研究院',
  },
  {
    quote:
      '免费档每天能翻 5 页足够试用，升级到 29 元月卡之后做文献调研效率翻倍。',
    author: '王博士',
    role: '中科院自动化所',
  },
] as const;

export function HomePage() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  const ctaTo = isAuthenticated ? '/translate' : '/register';
  const ctaLabel = isAuthenticated ? '继续翻译' : '免费开始使用';

  return (
    <div className="space-y-24 pb-16">
      <PageTitle
        title="科研论文 AI 翻译"
        description="公式保留 / 术语库 / 双语对照 — 面向科研论文的 AI 翻译平台"
      />
      <section className="relative overflow-hidden">
        <div
          aria-hidden="true"
          className="absolute inset-x-0 top-0 -z-10 h-[480px] bg-gradient-to-b from-brand-50 via-white to-transparent"
        />
        <div className="container-page pt-16 pb-12 sm:pt-24 sm:pb-16">
          <div className="grid items-center gap-12 lg:grid-cols-2">
            <div className="space-y-6">
              <span className="inline-flex items-center gap-2 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700">
                <Sparkles className="h-3.5 w-3.5" />
                公式保留 · 术语库 · 双语对照 · 多格式 PDF
              </span>
              <h1 className="text-balance text-4xl font-semibold tracking-tight text-ink-900 sm:text-5xl lg:text-6xl">
                科研论文 AI 翻译
                <br />
                <span className="text-brand-700">为学术写作而设计</span>
              </h1>
              <p className="max-w-xl text-pretty text-base text-ink-600 sm:text-lg">
                面向科研论文的 AI 翻译平台，保留数学公式、向量图表与参考文献，
                支持自定义术语库与多格式输出。让阅读与笔记更专注，让调研与综述更高效。
              </p>
              <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
                <Link to={ctaTo}>
                  <Button
                    size="lg"
                    rightIcon={<ArrowRight className="h-4 w-4" />}
                  >
                    {ctaLabel}
                  </Button>
                </Link>
                <Link to="/translate">
                  <Button size="lg" variant="secondary" leftIcon={<Languages className="h-4 w-4" />}>
                    直接上传 PDF
                  </Button>
                </Link>
              </div>
              <ul className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm text-ink-600 sm:max-w-md">
                {STATS.map((stat) => (
                  <li key={stat.label} className="flex items-baseline gap-2">
                    <span className="text-lg font-semibold text-ink-900">
                      {stat.value}
                    </span>
                    <span className="text-xs text-ink-500">{stat.label}</span>
                  </li>
                ))}
              </ul>
            </div>

            <HeroDemo />
          </div>
        </div>
      </section>

      <section className="container-page">
        <SectionHeader
          eyebrow="核心能力"
          title="把翻译这件小事做到严谨"
          description="论文翻译不是机翻。我们围绕学术写作的细节重新设计了整条流水线。"
        />
        <div className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((feature) => (
            <FeatureCard
              key={feature.title}
              icon={<feature.icon className="h-5 w-5" />}
              title={feature.title}
              description={feature.description}
            />
          ))}
        </div>
      </section>

      <section className="container-page">
        <SectionHeader
          eyebrow="工作流"
          title="上传到下载，三步即可完成"
          description="无需配置环境，无需本地 GPU。把 PDF 拖进网页，剩下的交给后端异步翻译集群。"
        />
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {WORKFLOW.map((step, idx) => (
            <Card key={step.title} className="flex flex-col gap-3">
              <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-sm font-semibold text-white">
                {idx + 1}
              </span>
              <h3 className="text-base font-semibold text-ink-900">
                {step.title}
              </h3>
              <p className="text-sm leading-6 text-ink-500">
                {step.description}
              </p>
            </Card>
          ))}
        </div>
      </section>

      <section className="container-page">
        <SectionHeader
          eyebrow="定价"
          title="为不同的翻译量提供合适的档位"
          description="免费档适合体验，付费档按月计费，随时升级或取消。"
        />
        <div className="mt-10">
          <PricingTable
            isAuthenticated={isAuthenticated}
            highlightPlan="standard"
          />
        </div>
      </section>

      <section className="container-page">
        <SectionHeader
          eyebrow="用户故事"
          title="来自一线的科研反馈"
          description="他们来自清华、复旦、中科院，把翻译交给 PaperTranslate，把时间留给自己。"
        />
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {TESTIMONIALS.map((item) => (
            <Card key={item.author} className="flex flex-col gap-4">
              <Quote
                className="h-5 w-5 text-brand-500"
                aria-hidden="true"
              />
              <p className="text-sm leading-6 text-ink-700">{item.quote}</p>
              <div className="mt-auto border-t border-ink-100 pt-3">
                <p className="text-sm font-medium text-ink-900">
                  {item.author}
                </p>
                <p className="text-xs text-ink-500">{item.role}</p>
              </div>
            </Card>
          ))}
        </div>
      </section>

      <section className="container-page">
        <Card className="flex flex-col items-start gap-6 p-8 md:flex-row md:items-center md:justify-between">
          <div className="flex items-start gap-4">
            <span className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-brand-50 text-brand-700">
              <ShieldCheck className="h-6 w-6" />
            </span>
            <div className="space-y-1">
              <h2 className="text-lg font-semibold text-ink-900">
                AGPL-3.0 开源透明
              </h2>
              <p className="text-sm text-ink-500">
                所有源码以 AGPL-3.0 协议开放，欢迎审计、贡献与自部署。
              </p>
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Link to="/billing">
              <Button variant="secondary" rightIcon={<ArrowRight className="h-4 w-4" />}>
                查看套餐
              </Button>
            </Link>
            <Link to="/register">
              <Button rightIcon={<ArrowRight className="h-4 w-4" />}>
                免费注册
              </Button>
            </Link>
          </div>
        </Card>
      </section>

      <section className="container-page">
        <Card
          padding="lg"
          className="flex flex-col items-center gap-4 text-center"
        >
          <span className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-ink-100 text-ink-500">
            <PlayCircle className="h-6 w-6" />
          </span>
          <h3 className="text-lg font-semibold text-ink-900">
            演示视频即将上线
          </h3>
          <p className="max-w-xl text-sm text-ink-500">
            我们正在录制 90 秒的端到端演示，涵盖上传 PDF、配置术语、实时进度、双语导出。
            视频发布后会同时出现在首页与帮助中心。
          </p>
        </Card>
      </section>
    </div>
  );
}

const WORKFLOW = [
  {
    title: '上传并选择选项',
    description:
      '拖拽 PDF 文件，设置源 / 目标语言、翻译服务与术语库，客户端会先校验大小与页数。',
  },
  {
    title: '实时查看进度',
    description:
      '通过 WebSocket 接收 0-100 进度，章节切换时同步提示当前正在翻译的页码范围。',
  },
  {
    title: '下载双语结果',
    description:
      '完成后可下载双 / 单语 PDF，链接 24 小时内有效。',
  },
] as const;

interface SectionHeaderProps {
  eyebrow: string;
  title: string;
  description: string;
}

const SectionHeader = memo(function SectionHeader({
  eyebrow,
  title,
  description,
}: SectionHeaderProps) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <span className="text-xs font-semibold uppercase tracking-wider text-brand-600">
        {eyebrow}
      </span>
      <h2 className="mt-3 text-2xl font-semibold tracking-tight text-ink-900 sm:text-3xl">
        {title}
      </h2>
      <p className="mt-3 text-sm text-ink-500 sm:text-base">{description}</p>
    </div>
  );
});

interface FeatureCardProps {
  icon: React.ReactNode;
  title: string;
  description: string;
}

const FeatureCard = memo(function FeatureCard({
  icon,
  title,
  description,
}: FeatureCardProps) {
  return (
    <Card className="flex flex-col gap-3">
      <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
        {icon}
      </span>
      <h3 className="text-base font-semibold text-ink-900">{title}</h3>
      <p className="text-sm leading-6 text-ink-500">{description}</p>
    </Card>
  );
});

const HeroDemo = memo(function HeroDemo() {
  return (
    <Card
      padding="none"
      className="relative overflow-hidden border-ink-200/70 bg-gradient-to-br from-white via-ink-50 to-brand-50"
    >
      <div className="flex items-center justify-between border-b border-ink-200 px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-brand-600 text-xs font-bold text-white">
            PT
          </span>
          <span className="text-sm font-medium text-ink-700">
            paper-2024-llm.pdf
          </span>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-brand-100 px-2.5 py-0.5 text-xs font-medium text-brand-700">
          <GraduationCap className="h-3 w-3" /> CS · 28 页
        </span>
      </div>
      <div className="space-y-3 p-6 text-sm leading-7 text-ink-700">
        <p className="font-mono text-xs text-ink-400">Abstract</p>
        <p>
          We propose a <strong className="text-brand-700">retrieval-augmented</strong>{' '}
          framework for long-context question answering, achieving{' '}
          <span className="rounded bg-ink-100 px-1.5 py-0.5 font-mono text-xs">
            +12.4 EM
          </span>{' '}
          on the QuALITY benchmark.
        </p>
        <p className="font-mono text-xs text-ink-400">译文</p>
        <p className="text-ink-900">
          我们提出了一种用于长上下文问答的
          <strong className="text-brand-700">检索增强</strong>
          框架，在 QuALITY 基准上取得了
          <span className="rounded bg-brand-100 px-1.5 py-0.5 font-mono text-xs text-brand-800">
            +12.4 EM
          </span>
          的提升。
        </p>
        <div className="grid grid-cols-3 gap-2 pt-2 text-xs">
          <Stat label="耗时" value="42 秒" />
          <Stat label="模型" value="DeepSeek-V3" />
          <Stat label="术语覆盖" value="98.6%" />
        </div>
      </div>
    </Card>
  );
});

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-ink-100 bg-white/80 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wider text-ink-400">{label}</p>
      <p className="mt-0.5 text-sm font-semibold text-ink-900">{value}</p>
    </div>
  );
}