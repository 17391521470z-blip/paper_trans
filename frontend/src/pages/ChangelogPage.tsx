import { useMemo } from 'react';
import { Sparkles } from 'lucide-react';

import { PageTitle } from '../components/seo/PageTitle';
import { CHANGELOG_ENTRIES, KIND_META } from '@/components/billing/changelog-data';
import { cn } from '@/lib/utils';

export function ChangelogPage() {
  // 按版本归组,版本号相同的几条合成一段
  const byVersion = useMemo(() => {
    const groups: Array<{ version: string; date: string; entries: typeof CHANGELOG_ENTRIES }> = [];
    const seen = new Map<string, number>();
    for (const entry of CHANGELOG_ENTRIES) {
      const key = entry.version || entry.date;
      const idx = seen.get(key);
      if (idx === undefined) {
        seen.set(key, groups.length);
        groups.push({
          version: entry.version || '—',
          date: entry.date,
          entries: [entry],
        });
      } else {
        groups[idx].entries.push(entry);
      }
    }
    return groups;
  }, []);

  return (
    <div className="container-page space-y-8 py-10 lg:py-12">
      <PageTitle
        title="更新记录"
        description="PaperTranslate 的版本变更、修复与新功能。"
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
              <Sparkles className="h-5 w-5" />
            </span>
            <h1 className="text-2xl font-semibold tracking-tight text-ink-900">
              更新记录
            </h1>
          </div>
          <p className="text-sm text-ink-500">
            共 {CHANGELOG_ENTRIES.length} 条更新 ·
            按版本号倒序排列,最新在上
          </p>
        </div>
      </div>

      {/* 按版本归组的卡片 */}
      <div className="space-y-6">
        {byVersion.map((group) => (
          <section key={group.version + group.date} className="space-y-3">
            <header className="flex flex-wrap items-center gap-3 border-b border-ink-100 pb-2">
              <h2 className="flex items-center gap-2 text-base font-semibold text-ink-900">
                <span className="font-mono text-sm">v{group.version}</span>
                <span className="text-ink-300">·</span>
                <time className="font-mono text-sm text-ink-500">{group.date}</time>
              </h2>
              <span className="ml-auto inline-flex items-center gap-1 text-xs text-ink-500">
                {group.entries.length} 条变更
              </span>
            </header>
            <ul className="space-y-2">
              {group.entries.map((entry) => {
                const { Icon, label, tone } = KIND_META[entry.kind];
                return (
                  <li
                    key={`${entry.date}-${entry.title}`}
                    className="rounded-lg border border-ink-200 bg-white p-4"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={cn(
                          'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium',
                          tone,
                        )}
                      >
                        <Icon className="h-3 w-3" />
                        {label}
                      </span>
                    </div>
                    <h3 className="mt-2 text-sm font-semibold text-ink-900">
                      {entry.title}
                    </h3>
                    <p className="mt-1 text-xs leading-5 text-ink-500">
                      {entry.description}
                    </p>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}

export default ChangelogPage;