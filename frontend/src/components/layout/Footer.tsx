import { Github, Mail } from 'lucide-react';
import { Link } from 'react-router-dom';

const PRODUCT_LINKS = [
  { to: '/translate', label: '开始翻译' },
  { to: '/glossaries', label: '术语库' },
  { to: '/billing', label: '订阅套餐' },
  { to: '/dashboard', label: '个人中心' },
];

const RESOURCE_LINKS = [
  { to: '/', label: '产品介绍' },
  { to: '/', label: '使用指南' },
  { to: '/', label: '更新日志' },
  { to: '/', label: 'API 文档' },
];

const LEGAL_LINKS = [
  { to: '/', label: '服务条款' },
  { to: '/', label: '隐私政策' },
  { to: '/about', label: 'AGPL-3.0 License' },
  { to: '/', label: '免责声明' },
];

const CONTACT_LINKS = [
  { href: 'mailto:hello@paper-translate.dev', label: 'hello@paper-translate.dev' },
  { href: 'https://github.com/your-org/paper-translate/issues', label: '提交问题' },
];

const SOURCE_CODE_URL = 'https://github.com/your-org/paper-translate';

export function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-ink-200 bg-white">
      <div className="container-page grid gap-10 py-12 md:grid-cols-4">
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-brand-700">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-brand-600 text-sm font-bold text-white">
              PT
            </span>
            <span className="text-base font-semibold">PaperTranslate</span>
          </div>
          <p className="text-sm leading-6 text-ink-500">
            面向科研论文的 AI 翻译平台，保留公式、图表与参考文献，支持自定义术语库与多格式导出。
          </p>
          <a
            href={SOURCE_CODE_URL}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-2 text-sm text-ink-600 hover:text-brand-700"
          >
            <Github className="h-4 w-4" />
            Source Code
          </a>
        </div>

        <FooterColumn title="产品" links={PRODUCT_LINKS} />
        <FooterColumn title="资源" links={RESOURCE_LINKS} />
        <div>
          <h4 className="mb-3 text-sm font-semibold text-ink-900">协议与联系</h4>
          <ul className="space-y-2">
            {LEGAL_LINKS.map((link) => (
              <li key={link.label}>
                <Link
                  to={link.to}
                  className="text-sm text-ink-500 hover:text-brand-700"
                >
                  {link.label}
                </Link>
              </li>
            ))}
            {CONTACT_LINKS.map((link) => (
              <li key={link.href}>
                <a
                  href={link.href}
                  className="inline-flex items-center gap-2 text-sm text-ink-500 hover:text-brand-700"
                >
                  {link.href.startsWith('mailto:') && (
                    <Mail className="h-3.5 w-3.5" />
                  )}
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="border-t border-ink-100 bg-ink-50">
        <div className="container-page flex flex-col items-start justify-between gap-2 py-4 text-xs text-ink-500 sm:flex-row sm:items-center">
          <p>
            &copy; {year} PaperTranslate Contributors. Released under the{' '}
            <a
              href="https://www.gnu.org/licenses/agpl-3.0.html"
              target="_blank"
              rel="noreferrer noopener"
              className="text-link"
            >
              AGPL-3.0 License
            </a>
            .
          </p>
          <p>
            源码以{' '}
            <a
              href={SOURCE_CODE_URL}
              target="_blank"
              rel="noreferrer noopener"
              className="text-link"
            >
              开放源代码
            </a>{' '}
            形式发布，欢迎贡献与审计。
          </p>
        </div>
      </div>
    </footer>
  );
}

interface FooterColumnProps {
  title: string;
  links: { to: string; label: string }[];
}

function FooterColumn({ title, links }: FooterColumnProps) {
  return (
    <div>
      <h4 className="mb-3 text-sm font-semibold text-ink-900">{title}</h4>
      <ul className="space-y-2">
        {links.map((link) => (
          <li key={link.label}>
            <Link
              to={link.to}
              className="text-sm text-ink-500 hover:text-brand-700"
            >
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}