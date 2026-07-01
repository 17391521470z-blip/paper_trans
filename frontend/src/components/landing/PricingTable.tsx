import { useCallback, memo } from 'react';
import { Link } from 'react-router-dom';
import { Check, Sparkles, X } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { cn } from '@/lib/utils';
import { PLAN_DEFINITIONS, type PlanCode } from '@/lib/constants';

export interface PricingTableProps {
  currentPlan?: PlanCode | string | null;
  isAuthenticated?: boolean;
  highlightPlan?: PlanCode;
  onSelect?: (plan: PlanCode) => void;
  compact?: boolean;
}

interface PlanRow {
  label: string;
  values: Record<PlanCode, boolean | string>;
}

const COMPARISON_ROWS: PlanRow[] = [
  {
    label: '月翻译配额',
    values: { free: '30 页', standard: '200 页', pro: '800 页' },
  },
  {
    label: '日翻译配额',
    values: { free: '5 页', standard: '50 页', pro: '200 页' },
  },
  {
    label: '自定义术语库',
    values: { free: '1 个', standard: '5 个', pro: '20 个' },
  },
  {
    label: '公式与图表保留',
    values: { free: true, standard: true, pro: true },
  },
  {
    label: '参考文献自动跳过',
    values: { free: true, standard: true, pro: true },
  },
  {
    label: '双 / 单语 PDF 导出',
    values: { free: true, standard: true, pro: true },
  },
  {
    label: '优先队列',
    values: { free: false, standard: false, pro: true },
  },
  {
    label: '7×24 优先支持',
    values: { free: false, standard: false, pro: true },
  },
];

export const PricingTable = memo(function PricingTable({
  currentPlan,
  isAuthenticated = false,
  highlightPlan = 'standard',
  onSelect,
  compact = false,
}: PricingTableProps) {
  return (
    <div className="space-y-8">
      <div
        className={cn(
          'grid gap-4 md:gap-6',
          compact ? 'md:grid-cols-3' : 'md:grid-cols-3',
        )}
      >
        {PLAN_DEFINITIONS.map((plan) => (
          <PlanCard
            key={plan.code}
            code={plan.code}
            currentPlan={currentPlan ?? null}
            isAuthenticated={isAuthenticated}
            highlightPlan={highlightPlan}
            onSelect={onSelect}
          />
        ))}
      </div>

      {!compact && (
        <Card padding="none" className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="bg-ink-50 text-ink-700">
                  <th className="w-1/3 px-6 py-3 font-medium">能力对比</th>
                  {PLAN_DEFINITIONS.map((plan) => (
                    <th
                      key={plan.code}
                      className="px-6 py-3 text-center font-medium"
                    >
                      {plan.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {COMPARISON_ROWS.map((row, idx) => (
                  <tr
                    key={row.label}
                    className={cn(idx > 0 && 'border-t border-ink-100')}
                  >
                    <td className="px-6 py-3 text-ink-700">{row.label}</td>
                    {PLAN_DEFINITIONS.map((plan) => (
                      <td key={plan.code} className="px-6 py-3 text-center">
                        <FeatureCell value={row.values[plan.code]} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
});

interface PlanCardProps {
  code: PlanCode;
  currentPlan: PlanCode | string | null;
  isAuthenticated: boolean;
  highlightPlan: PlanCode;
  onSelect?: (plan: PlanCode) => void;
}

const PlanCard = memo(function PlanCard({
  code,
  currentPlan,
  isAuthenticated,
  highlightPlan,
  onSelect,
}: PlanCardProps) {
  const plan = PLAN_DEFINITIONS.find((p) => p.code === code);
  if (!plan) return null;

  const isHighlight = plan.code === highlightPlan;
  const isCurrent = plan.code === currentPlan;

  const handleClick = useCallback(() => {
    onSelect?.(plan.code);
  }, [onSelect, plan.code]);

  const ctaLabel = isCurrent
    ? '当前套餐'
    : plan.code === 'free'
      ? '免费使用'
      : `升级到 ${plan.name}`;

  return (
    <Card
      className={cn(
        'relative flex flex-col gap-5',
        isHighlight && 'border-brand-500 shadow-card ring-2 ring-brand-500/30',
      )}
    >
      {isHighlight && (
        <span className="absolute -top-3 left-1/2 inline-flex -translate-x-1/2 items-center gap-1 rounded-full bg-brand-600 px-3 py-1 text-xs font-medium text-white shadow-card">
          <Sparkles className="h-3 w-3" /> 推荐
        </span>
      )}
      <div className="space-y-2">
        <h3 className="text-base font-semibold text-ink-900">{plan.name}</h3>
        <p className="text-sm text-ink-500">
          {plan.code === 'free'
            ? '适合体验和轻度使用'
            : plan.code === 'standard'
              ? '适合硕博生与课题组'
              : '适合重度科研用户与机构'}
        </p>
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-3xl font-semibold text-ink-900">
          {plan.priceLabel}
        </span>
        <span className="text-sm text-ink-500">{plan.periodLabel}</span>
      </div>
      <ul className="space-y-2 text-sm text-ink-600">
        {plan.features.map((feature) => (
          <li key={feature} className="flex items-start gap-2">
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
            <span>{feature}</span>
          </li>
        ))}
      </ul>
      <div className="mt-auto pt-2">
        {onSelect ? (
          <Button
            fullWidth
            variant={isHighlight ? 'primary' : 'secondary'}
            disabled={isCurrent}
            onClick={handleClick}
          >
            {ctaLabel}
          </Button>
        ) : (
          <Link
            to={
              plan.code === 'free'
                ? isAuthenticated
                  ? '/dashboard'
                  : '/register'
                : isAuthenticated
                  ? '/billing'
                  : '/register'
            }
            className="block"
          >
            <Button
              fullWidth
              variant={isHighlight ? 'primary' : 'secondary'}
              disabled={isCurrent}
            >
              {ctaLabel}
            </Button>
          </Link>
        )}
      </div>
    </Card>
  );
});

interface FeatureCellProps {
  value: boolean | string;
}

const FeatureCell = memo(function FeatureCell({ value }: FeatureCellProps) {
  if (typeof value === 'boolean') {
    return value ? (
      <Check
        className="mx-auto h-4 w-4 text-brand-600"
        aria-label="包含"
      />
    ) : (
      <X
        className="mx-auto h-4 w-4 text-ink-300"
        aria-label="不包含"
      />
    );
  }
  return <span className="text-ink-700">{value}</span>;
});