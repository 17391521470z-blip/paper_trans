import { memo } from 'react';
import { Sparkles } from 'lucide-react';

import { Card } from '@/components/ui/Card';
import { cn } from '@/lib/utils';
import {
  CHANGELOG_ENTRIES,
  KIND_META,
  type ChangelogEntry,
} from './changelog-data';

interface ChangelogPanelProps {
  /** 默认展示最近 6 条(最新在前);传 0 或负数表示全部 */
  limit?: number;
  className?: string;
  /** 是否显示 header(订阅页侧栏用 false 让父组件管) */
  showHeader?: boolean;
}

export function ChangelogPanel({
  limit = 6,
  className,
  showHeader = true,
}: ChangelogPanelProps) {
  const entries = limit > 0 ? CHANGELOG_ENTRIES.slice(0, limit) : CHANGELOG_ENTRIES;

  return (
    <Card padding="lg" className={cn('space-y-5', className)}>
      {showHeader && (
        <header className="space-y-1">
          <h2 className="flex items-center gap-2 text-base font-semibold text-ink-900">
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
              <Sparkles className="h-4 w-4" />
            </span>
            更新记录
          </h2>
          <p className="text-xs text-ink-500">最近 6 次发布与修复</p>
        </header>
      )}

      <ol className="relative space-y-4 border-l border-ink-100 pl-5">
        {entries.map((entry) => (
          <ChangelogItem key={`${entry.date}-${entry.title}`} entry={entry} />
        ))}
      </ol>
    </Card>
  );
}

interface ChangelogItemProps {
  entry: ChangelogEntry;
}

const ChangelogItem = memo(function ChangelogItem({ entry }: ChangelogItemProps) {
  const { Icon, label, tone } = KIND_META[entry.kind];
  return (
    <li className="relative">
      <span className="absolute -left-[27px] top-1 inline-flex h-4 w-4 items-center justify-center rounded-full border-2 border-white bg-brand-500" />
      <div className="flex flex-wrap items-center gap-2">
        <time className="font-mono text-xs text-ink-500">{entry.date}</time>
        {entry.version && (
          <span className="rounded bg-ink-100 px-1.5 py-0.5 font-mono text-[10px] text-ink-600">
            v{entry.version}
          </span>
        )}
        <span
          className={cn(
            'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium',
            tone,
          )}
        >
          <Icon className="h-3 w-3" />
          {label}
        </span>
      </div>
      <h3 className="mt-1 text-sm font-medium text-ink-900">{entry.title}</h3>
      <p className="mt-0.5 text-xs leading-5 text-ink-500">{entry.description}</p>
    </li>
  );
});

export default ChangelogPanel;