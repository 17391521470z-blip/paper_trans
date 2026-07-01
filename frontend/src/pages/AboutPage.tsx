import { BookOpen, Code2, Github, Heart, Mail, ShieldCheck } from 'lucide-react';

import { PageTitle } from '../components/seo/PageTitle';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';

const SOURCE_CODE_URL = 'https://github.com/your-org/paper-translate';

const TECH_STACK = [
  { category: '前端框架', items: 'React 18 + TypeScript + Vite' },
  { category: '样式方案', items: 'Tailwind CSS 3 + clsx + tailwind-merge' },
  { category: '状态管理', items: 'Zustand 5' },
  { category: '路由', items: 'React Router v6' },
  { category: 'HTTP 客户端', items: 'Axios' },
  { category: 'PDF 引擎', items: 'react-pdf + PDF.js' },
  { category: '后端框架', items: 'Python FastAPI' },
  { category: '翻译引擎', items: 'DeepSeek / GLM / OpenAI 兼容 API' },
  { category: '文档解析', items: 'BabelDOC + DocLayout-YOLO' },
  { category: '数据库', items: 'PostgreSQL + Redis' },
] as const;

const CONTRIBUTION_GUIDELINES = [
  'Fork 仓库并创建功能分支',
  '遵循现有的代码风格与提交规范',
  '为新增功能编写测试用例',
  '提交 Pull Request 并描述改动内容',
  '等待 Code Review 与 CI 通过后合并',
];

export function AboutPage() {
  return (
    <div className="container-page space-y-10 py-10 lg:py-12">
      <PageTitle title="关于" />
      <header className="max-w-2xl">
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-ink-900">
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
            <BookOpen className="h-5 w-5" />
          </span>
          关于 PaperTranslate
        </h1>
        <p className="mt-2 text-sm text-ink-500">
          面向科研论文的 AI 翻译平台 —— 保留公式、图表与参考文献结构，让学术阅读与写作更高效。
        </p>
      </header>

      <section className="grid gap-6 lg:grid-cols-2">
        <Card padding="lg" className="flex flex-col gap-4">
          <h2 className="flex items-center gap-2 text-lg font-semibold text-ink-900">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
              <ShieldCheck className="h-4 w-4" />
            </span>
            AGPL-3.0 开源协议
          </h2>
          <div className="space-y-3 text-sm leading-7 text-ink-600">
            <p>
              PaperTranslate 是开源软件，以
              <a
                href="https://www.gnu.org/licenses/agpl-3.0.html"
                target="_blank"
                rel="noreferrer noopener"
                className="text-link mx-1"
              >
                GNU Affero General Public License v3.0
              </a>
              协议发布。
            </p>
            <p>
              这意味着你可以自由地使用、修改、分发本软件，但任何基于本软件的修改版本或
              派生作品如果通过网络提供服务，也必须以 AGPL-3.0 协议向所有用户开放源代码。
            </p>
            <p>
              完整源码可在
              <a
                href={SOURCE_CODE_URL}
                target="_blank"
                rel="noreferrer noopener"
                className="text-link mx-1"
              >
                此处
              </a>
              获取。
            </p>
          </div>
        </Card>

        <Card padding="lg" className="flex flex-col gap-4">
          <h2 className="flex items-center gap-2 text-lg font-semibold text-ink-900">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
              <Heart className="h-4 w-4" />
            </span>
            开源贡献指南
          </h2>
          <p className="text-sm text-ink-500">
            欢迎任何形式的贡献 —— 功能建议、Bug 报告、文档改进、代码提交都对我们很有帮助。
          </p>
          <ol className="space-y-2 text-sm text-ink-600">
            {CONTRIBUTION_GUIDELINES.map((step, idx) => (
              <li key={step} className="flex items-start gap-2">
                <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">
                  {idx + 1}
                </span>
                {step}
              </li>
            ))}
          </ol>
          <div className="mt-2">
            <a
              href={SOURCE_CODE_URL}
              target="_blank"
              rel="noreferrer noopener"
            >
              <Button
                variant="secondary"
                leftIcon={<Github className="h-4 w-4" />}
              >
                前往 GitHub 仓库
              </Button>
            </a>
          </div>
        </Card>
      </section>

      <section>
        <h2 className="mb-4 text-lg font-semibold text-ink-900">技术栈</h2>
        <Card padding="none">
          <div className="divide-y divide-ink-100">
            {TECH_STACK.map((item) => (
              <div
                key={item.category}
                className="flex items-baseline justify-between px-5 py-3 text-sm"
              >
                <span className="font-medium text-ink-700">{item.category}</span>
                <span className="text-ink-500">{item.items}</span>
              </div>
            ))}
          </div>
        </Card>
      </section>

      <section>
        <Card padding="lg" className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
              <Mail className="h-5 w-5" />
            </span>
            <div>
              <h2 className="text-base font-semibold text-ink-900">联系我们</h2>
              <p className="mt-1 text-sm text-ink-500">
                问题反馈、功能建议或商务合作，欢迎发送邮件。
              </p>
            </div>
          </div>
          <a href="mailto:hello@paper-translate.dev">
            <Button variant="secondary" leftIcon={<Mail className="h-4 w-4" />}>
              hello@paper-translate.dev
            </Button>
          </a>
        </Card>
      </section>

      <section className="flex items-center justify-center gap-2 text-sm text-ink-400">
        <Code2 className="h-4 w-4" />
        <span>
          以
          <a
            href={SOURCE_CODE_URL}
            target="_blank"
            rel="noreferrer noopener"
            className="text-link mx-1"
          >
            开源
          </a>
          的方式构建，为科研而生。
        </span>
      </section>
    </div>
  );
}
