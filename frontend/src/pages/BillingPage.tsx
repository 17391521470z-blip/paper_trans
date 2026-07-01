import { memo, useCallback, useEffect, useState } from 'react';
import {
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  CreditCard,
  Smartphone,
  X,
} from 'lucide-react';
import { toast } from 'sonner';

import { PageTitle } from '../components/seo/PageTitle';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { cn } from '@/lib/utils';
import { PLAN_DEFINITIONS, type PlanCode } from '@/lib/constants';
import { useAuthStore } from '@/stores/authStore';
import { useQuotaStore } from '@/stores/quotaStore';
import { useOrderStore, type Order, type PaymentMethod } from '@/stores/orderStore';
import { PricingTable } from '@/components/landing/PricingTable';
import { getErrorMessage } from '@/lib/errorHandler';

const STATUS_LABELS: Record<Order['status'], string> = {
  pending: '待支付',
  paid: '已支付',
  refunded: '已退款',
  cancelled: '已取消',
  expired: '已过期',
};

const STATUS_TONE: Record<Order['status'], string> = {
  pending: 'bg-amber-100 text-amber-700',
  paid: 'bg-emerald-100 text-emerald-700',
  refunded: 'bg-ink-100 text-ink-700',
  cancelled: 'bg-ink-100 text-ink-500',
  expired: 'bg-red-100 text-red-700',
};

const METHOD_LABELS: Record<PaymentMethod, string> = {
  wechat: '微信支付',
  alipay: '支付宝',
};

export function BillingPage() {
  const user = useAuthStore((s) => s.user);
  const quota = useQuotaStore((s) => s.quota);
  const refreshQuota = useQuotaStore((s) => s.refresh);

  const orders = useOrderStore((s) => s.orders);
  const isLoadingOrders = useOrderStore((s) => s.isLoading);
  const fetchList = useOrderStore((s) => s.fetchList);

  const [selectedPlan, setSelectedPlan] = useState<PlanCode | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('wechat');
  const [showCheckout, setShowCheckout] = useState(false);

  useEffect(() => {
    void refreshQuota();
    void fetchList();
  }, [fetchList, refreshQuota]);

  const handleSelect = useCallback((plan: PlanCode) => {
    if (plan === 'free') {
      toast.info('免费档无需购买，登录即可使用');
      return;
    }
    setSelectedPlan(plan);
    setShowCheckout(true);
  }, []);

  const currentPlan = ((user?.plan ?? quota?.tier ?? 'free') as string).toLowerCase() as PlanCode;

  return (
    <div className="container-page space-y-10 py-10 lg:py-12">
      <PageTitle title="订阅与支付" />
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-ink-900">
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
            <CreditCard className="h-5 w-5" />
          </span>
          订阅与支付
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          按月计费，随时升级或降级，已支付订单可在订单历史中查看。
        </p>
      </header>

      <Card padding="lg">
        <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-wider text-ink-400">当前套餐</p>
            <p className="mt-1 text-2xl font-semibold text-ink-900">
              {PLAN_DEFINITIONS.find((p) => p.code === currentPlan)?.name ?? currentPlan}
            </p>
            <ul className="mt-3 space-y-1 text-sm text-ink-500">
              <li>
                月配额：{quota?.monthly_pages ?? '—'} 页
              </li>
              <li>
                已使用：{quota?.used_pages ?? 0} 页
              </li>
              <li className="flex items-center gap-1.5">
                <CalendarClock className="h-3.5 w-3.5" />
                {quota?.reset_at
                  ? `下次重置：${new Date(quota.reset_at).toLocaleDateString()}`
                  : '免费档按月重置'}
              </li>
            </ul>
          </div>
          <div className="flex flex-col items-end gap-2">
            {currentPlan === 'free' ? (
              <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
                免费档每月仅 30 页，升级后翻译更自由
              </p>
            ) : (
              <p className="rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
                已订阅付费档，感谢支持
              </p>
            )}
            <Button
              variant="secondary"
              onClick={() => handleSelect(currentPlan === 'free' ? 'standard' : 'pro')}
            >
              {currentPlan === 'free' ? '升级套餐' : '续费 / 变更套餐'}
            </Button>
          </div>
        </div>
      </Card>

      <div className="grid items-start gap-6 lg:grid-cols-5">
        <div className="space-y-10 lg:col-span-5">
          <section>
            <h2 className="text-lg font-semibold text-ink-900">套餐对比</h2>
            <p className="mt-1 text-sm text-ink-500">
              所有付费档含双 / 单语 PDF 导出；Pro 档享优先队列与 7×24 支持。
            </p>
            <div className="mt-6">
              <PricingTable
                isAuthenticated={true}
                currentPlan={currentPlan}
                highlightPlan="standard"
                onSelect={handleSelect}
              />
            </div>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-ink-900">订单历史</h2>
            <Card padding="none" className="mt-4">
              {isLoadingOrders && orders.length === 0 ? (
                <div className="flex items-center justify-center py-10">
                  <Spinner label="正在加载订单…" />
                </div>
              ) : orders.length === 0 ? (
                <p className="px-5 py-10 text-center text-sm text-ink-500">
                  暂无订单记录
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px] text-left text-sm">
                    <thead className="bg-ink-50 text-ink-600">
                      <tr>
                        <th className="px-5 py-3 font-medium">订单号</th>
                        <th className="px-5 py-3 font-medium">套餐</th>
                        <th className="px-5 py-3 font-medium">金额</th>
                        <th className="px-5 py-3 font-medium">支付方式</th>
                        <th className="px-5 py-3 font-medium">状态</th>
                        <th className="px-5 py-3 font-medium">创建时间</th>
                      </tr>
                    </thead>
                    <tbody>
                      {orders.map((o) => (
                        <OrderRow key={o.id} order={o} />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </section>
        </div>
      </div>

      {showCheckout && selectedPlan && (
        <CheckoutModal
          plan={selectedPlan}
          paymentMethod={paymentMethod}
          onPaymentChange={setPaymentMethod}
          onClose={() => setShowCheckout(false)}
        />
      )}
    </div>
  );
}

interface OrderRowProps {
  order: Order;
}

const OrderRow = memo(function OrderRow({ order }: OrderRowProps) {
  return (
    <tr className="border-t border-ink-100 text-ink-700">
      <td className="px-5 py-3 font-mono text-xs">{order.order_no}</td>
      <td className="px-5 py-3 text-ink-900">
        {PLAN_DEFINITIONS.find((p) => p.code === order.tier)?.name ?? order.tier}
      </td>
      <td className="px-5 py-3 font-medium text-ink-900">
        ¥{order.amount_cny.toFixed(2)}
      </td>
      <td className="px-5 py-3 text-ink-500">{METHOD_LABELS[order.payment_method]}</td>
      <td className="px-5 py-3">
        <span
          className={cn(
            'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
            STATUS_TONE[order.status],
          )}
        >
          {order.status === 'paid' && <CheckCircle2 className="h-3 w-3" />}
          {STATUS_LABELS[order.status]}
        </span>
      </td>
      <td className="px-5 py-3 text-ink-500">
        {order.created_at ? new Date(order.created_at).toLocaleString() : '—'}
      </td>
    </tr>
  );
});

interface CheckoutModalProps {
  plan: PlanCode;
  paymentMethod: PaymentMethod;
  onPaymentChange: (method: PaymentMethod) => void;
  onClose: () => void;
}

function CheckoutModal({
  plan,
  paymentMethod,
  onPaymentChange,
  onClose,
}: CheckoutModalProps) {
  const planDef = PLAN_DEFINITIONS.find((p) => p.code === plan);
  const createOrder = useOrderStore((s) => s.createOrder);
  const currentOrder = useOrderStore((s) => s.currentOrder);
  const isCreating = useOrderStore((s) => s.isCreating);
  const clearCurrent = useOrderStore((s) => s.clearCurrent);

  const [stage, setStage] = useState<'select' | 'paying'>('select');

  useEffect(() => {
    return () => clearCurrent();
  }, [clearCurrent]);

  const handleCreate = useCallback(async () => {
    try {
      await createOrder(plan, paymentMethod, 1);
      setStage('paying');
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  }, [createOrder, paymentMethod, plan]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 px-4"
    >
      <Card className="w-full max-w-lg p-6">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-ink-900">升级到 {planDef?.name}</h2>
            <p className="mt-1 text-sm text-ink-500">
              {planDef?.priceLabel} / 月 · {planDef?.periodLabel}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-ink-400 hover:bg-ink-100"
            aria-label="关闭弹窗"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {stage === 'select' && (
          <div className="space-y-4">
            <div>
              <p className="mb-2 text-sm font-medium text-ink-700">选择支付方式</p>
              <div className="grid gap-2 sm:grid-cols-2">
                <PaymentOption
                  selected={paymentMethod === 'wechat'}
                  onClick={() => onPaymentChange('wechat')}
                  label="微信支付"
                  icon={<Smartphone className="h-4 w-4" />}
                />
                <PaymentOption
                  selected={paymentMethod === 'alipay'}
                  onClick={() => onPaymentChange('alipay')}
                  label="支付宝"
                  icon={<CreditCard className="h-4 w-4" />}
                />
              </div>
            </div>

            <div className="rounded-lg bg-ink-50 px-4 py-3 text-sm text-ink-600">
              <p className="flex items-center justify-between">
                <span>应付金额</span>
                <span className="text-base font-semibold text-ink-900">
                  ¥{planDef?.priceCny ?? 0}
                </span>
              </p>
              <p className="mt-1 text-xs text-ink-500">
                订阅按月续费，可随时取消。
              </p>
            </div>

            <div className="flex items-center justify-end gap-2">
              <Button variant="secondary" onClick={onClose} disabled={isCreating}>
                取消
              </Button>
              <Button onClick={handleCreate} isLoading={isCreating}>
                {isCreating ? '正在创建订单…' : '下一步 · 扫码支付'}
              </Button>
            </div>
          </div>
        )}

        {stage === 'paying' && currentOrder && (
          <div className="space-y-4 text-center">
            <p className="text-sm font-medium text-ink-900">请使用{METHOD_LABELS[currentOrder.payment_method]}扫码支付</p>
            {currentOrder.qr_code_url ? (
              <div className="mx-auto flex h-48 w-48 items-center justify-center rounded-xl border border-ink-200 bg-white">
                <img
                  src={currentOrder.qr_code_url}
                  alt="支付二维码"
                  className="h-44 w-44"
                />
              </div>
            ) : (
              <div className="mx-auto flex h-48 w-48 items-center justify-center rounded-xl border border-dashed border-ink-200 bg-ink-50 text-sm text-ink-500">
                二维码生成中…
              </div>
            )}
            <p className="text-xs text-ink-500">
              订单号 <span className="font-mono">{currentOrder.order_no}</span>，
              {currentOrder.expires_at
                ? `请于 ${new Date(currentOrder.expires_at).toLocaleString()} 前完成支付`
                : '订单 24 小时内有效'}
            </p>
            <div className="flex items-center justify-center gap-2 pt-2">
              <Button variant="secondary" onClick={onClose}>
                已完成支付
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setStage('select');
                  clearCurrent();
                }}
              >
                返回
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

interface PaymentOptionProps {
  selected: boolean;
  onClick: () => void;
  label: string;
  icon: React.ReactNode;
}

function PaymentOption({ selected, onClick, label, icon }: PaymentOptionProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        'flex items-center justify-between rounded-lg border bg-white px-3 py-2.5 text-sm font-medium transition-colors',
        selected
          ? 'border-brand-500 bg-brand-50 text-brand-700 ring-1 ring-brand-500/30'
          : 'border-ink-200 text-ink-700 hover:border-brand-300',
      )}
    >
      <span className="inline-flex items-center gap-2">
        <span className="text-brand-600">{icon}</span>
        {label}
      </span>
      <ChevronDown
        className={cn(
          'h-4 w-4 text-ink-300 transition-transform',
          selected && 'rotate-180 text-brand-600',
        )}
      />
    </button>
  );
}