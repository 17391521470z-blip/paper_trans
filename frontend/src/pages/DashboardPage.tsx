import { memo, useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  CreditCard,
  FileText,
  LayoutDashboard,
  RefreshCw,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';

import { PageTitle } from '../components/seo/PageTitle';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader } from '@/components/ui/Card';
import { DownloadMenu } from '@/components/download/DownloadMenu';
import { Spinner } from '@/components/ui/Spinner';
import { cn, formatBytes, formatPercent } from '@/lib/utils';
import { apiGet, apiDelete } from '@/lib/api';
import { useAuthStore } from '@/stores/authStore';
import { useQuotaStore } from '@/stores/quotaStore';
import { type TaskInfo, type TaskStatus } from '@/stores/taskStore';

interface TaskListResponse {
  items: TaskInfo[];
  page: number;
  page_size: number;
  total: number;
}

const STATUS_LABELS: Record<TaskStatus, string> = {
  idle: '空闲',
  uploading: '上传中',
  pending: '排队中',
  processing: '翻译中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
};

const STATUS_TONE: Record<TaskStatus, string> = {
  idle: 'bg-ink-100 text-ink-700',
  uploading: 'bg-amber-100 text-amber-700',
  pending: 'bg-amber-100 text-amber-700',
  processing: 'bg-brand-100 text-brand-700',
  completed: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-red-100 text-red-700',
  cancelled: 'bg-ink-100 text-ink-500',
};

const PLAN_LABELS: Record<string, string> = {
  free: '免费档',
  standard: '标准档',
  pro: 'Pro 档',
};

const PAGE_SIZE = 10;

export function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const fetchProfile = useAuthStore((s) => s.fetchProfile);
  const quota = useQuotaStore((s) => s.quota);
  const quotaLoading = useQuotaStore((s) => s.isLoading);
  const refreshQuota = useQuotaStore((s) => s.refresh);

  // 列表数据完全由本页自管,不再订阅 taskStore 的 recentTasks / listPage。
  // 原因:TranslatePage 与 DashboardPage 共享 taskStore,后者调用
  // fetchRecentTasks(1, 4) 会覆盖 listPage/listPageSize/listTotal,造成
  // DashboardPage 的 currentPage 与 totalPages 计算异常。

  const [recentTasks, setRecentTasks] = useState<TaskInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [page, setPage] = useState(1);

  const fetchPage = useCallback(
    async (pageToFetch: number, pageSize = PAGE_SIZE) => {
      setTasksLoading(true);
      try {
        const res = await apiGet<TaskListResponse>(
          `/tasks?page=${pageToFetch}&page_size=${pageSize}`,
        );
        setRecentTasks(res.items);
        setTotal(res.total);
      } finally {
        setTasksLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    void fetchProfile();
    void refreshQuota();
  }, [fetchProfile, refreshQuota]);

  useEffect(() => {
    void fetchPage(page);
  }, [fetchPage, page]);

  const handleRefresh = useCallback(() => {
    void refreshQuota();
    void fetchPage(page);
  }, [fetchPage, page, refreshQuota]);

  const handleDelete = useCallback(
    async (taskId: string) => {
      try {
        await apiDelete<void>(`/tasks/${taskId}`);
        toast.success('任务已删除');
        // 如果当前页删完是空的且有更早页,回退一页
        if (recentTasks.length <= 1 && page > 1) {
          setPage((p) => Math.max(1, p - 1));
        } else {
          await fetchPage(page);
        }
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '删除失败');
      }
    },
    [apiDelete, fetchPage, page, recentTasks.length],
  );

  const monthly = quota?.monthly_pages ?? 0;
  const used = quota?.used_pages ?? 0;
  const remaining = quota?.remaining_pages ?? 0;
  const usedPercent = monthly > 0 ? Math.min(100, Math.round((used / monthly) * 100)) : 0;
  const daily = quota?.daily_pages ?? 0;
  const usedDaily = quota?.used_daily_pages ?? 0;
  const dailyPercent = daily > 0 ? Math.min(100, Math.round((usedDaily / daily) * 100)) : 0;
  const tier = (quota?.tier ?? user?.plan ?? 'free') as string;
  const renewAt = quota?.reset_at ? new Date(quota.reset_at) : null;

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="container-page space-y-8 py-10 lg:py-12">
      <PageTitle title="用户中心" />
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-ink-900">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
              <LayoutDashboard className="h-5 w-5" />
            </span>
            个人中心
          </h1>
          <p className="mt-1 text-sm text-ink-500">
            {user?.display_name ? `欢迎回来，${user.display_name}` : '欢迎使用 PaperTranslate'}
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={handleRefresh}
          leftIcon={<RefreshCw className="h-4 w-4" />}
        >
          刷新数据
        </Button>
      </header>

      <section className="grid gap-4 lg:grid-cols-3">
        <Card padding="lg" className="lg:col-span-2">
          <CardHeader
            title={
              <span className="flex items-center gap-2 text-base font-semibold text-ink-900">
                <Activity className="h-4 w-4 text-brand-600" />
                本月翻译配额
              </span>
            }
            description={`当前套餐：${PLAN_LABELS[tier] ?? tier}`}
          />
          {quotaLoading && !quota ? (
            <div className="mt-6 flex items-center justify-center py-8">
              <Spinner label="正在获取配额…" />
            </div>
          ) : (
            <div className="mt-4 space-y-5">
              <UsageBar
                label="本月已用"
                used={used}
                total={monthly}
                percent={usedPercent}
                tone="brand"
              />
              <UsageBar
                label="今日已用"
                used={usedDaily}
                total={daily}
                percent={dailyPercent}
                tone="amber"
              />
              <div className="grid gap-3 sm:grid-cols-3">
                <Metric label="本月剩余" value={`${remaining} 页`} />
                <Metric label="今日剩余" value={`${quota?.remaining_daily_pages ?? 0} 页`} />
                <Metric
                  label="下次重置"
                  value={renewAt ? renewAt.toLocaleDateString() : '下月 1 号'}
                />
              </div>
            </div>
          )}
        </Card>

        <Card padding="lg" className="flex flex-col">
          <CardHeader
            title={
              <span className="flex items-center gap-2 text-base font-semibold text-ink-900">
                <CreditCard className="h-4 w-4 text-brand-600" />
                套餐信息
              </span>
            }
            description="按月计费，随时升级或降级"
          />
          <div className="mt-4 flex flex-1 flex-col justify-between gap-4">
            <div className="space-y-2">
              <p className="text-2xl font-semibold text-ink-900">
                {PLAN_LABELS[tier] ?? tier}
              </p>
              <p className="text-xs text-ink-500">
                月配额 {monthly} 页 · 每日 {daily} 页
              </p>
            </div>
            <div className="flex flex-col gap-2">
              <Link to="/billing">
                <Button fullWidth rightIcon={<ArrowRight className="h-4 w-4" />}>
                  {tier === 'free' ? '升级套餐' : '管理订阅'}
                </Button>
              </Link>
              {tier !== 'free' && (
                <Link to="/billing">
                  <Button fullWidth variant="secondary">
                    查看续费时间
                  </Button>
                </Link>
              )}
            </div>
          </div>
        </Card>
      </section>

      <section>
        <Card padding="none">
          <div className="flex flex-col gap-2 border-b border-ink-100 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
            <CardHeader
              title={
                <span className="flex items-center gap-2 text-base font-semibold text-ink-900">
                  <FileText className="h-4 w-4 text-brand-600" />
                  历史任务
                </span>
              }
              description={`共 ${total} 条记录`}
            />
            <Link to="/translate">
              <Button variant="secondary" size="sm" leftIcon={<Sparkles className="h-4 w-4" />}>
                开始新任务
              </Button>
            </Link>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="bg-ink-50 text-ink-600">
                <tr>
                  <th className="px-5 py-3 font-medium">文件名</th>
                  <th className="px-5 py-3 font-medium">状态</th>
                  <th className="px-5 py-3 font-medium">页数</th>
                  <th className="px-5 py-3 font-medium">大小</th>
                  <th className="px-5 py-3 font-medium">提交时间</th>
                  <th className="px-5 py-3 font-medium text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {tasksLoading && recentTasks.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-5 py-10 text-center text-ink-500">
                      <Spinner label="正在加载历史任务…" />
                    </td>
                  </tr>
                ) : recentTasks.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-5 py-10 text-center text-ink-500">
                      还没有任何任务记录，去
                      <Link to="/translate" className="text-link mx-1">
                        翻译页
                      </Link>
                      开始第一次翻译吧。
                    </td>
                  </tr>
                ) : (
                  recentTasks.map((task) => (
                    <TaskRow
                      key={task.id}
                      task={task}
                      onDelete={handleDelete}
                    />
                  ))
                )}
              </tbody>
            </table>
          </div>

          {total > 0 && (
            <div className="flex items-center justify-between border-t border-ink-100 px-5 py-3 text-sm text-ink-500">
              <span>
                第 {page} / {totalPages} 页
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={page <= 1 || tasksLoading}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  leftIcon={<ChevronLeft className="h-4 w-4" />}
                >
                  上一页
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={page >= totalPages || tasksLoading}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  rightIcon={<ChevronRight className="h-4 w-4" />}
                >
                  下一页
                </Button>
              </div>
            </div>
          )}
        </Card>
      </section>
    </div>
  );
}

interface UsageBarProps {
  label: string;
  used: number;
  total: number;
  percent: number;
  tone: 'brand' | 'amber';
}

const UsageBar = memo(function UsageBar({
  label,
  used,
  total,
  percent,
  tone,
}: UsageBarProps) {
  const fillClass = tone === 'brand' ? 'bg-brand-600' : 'bg-amber-500';
  return (
    <div>
      <div className="flex items-center justify-between text-sm">
        <span className="text-ink-600">{label}</span>
        <span className="font-medium text-ink-900">
          {used} / {total} 页 · {formatPercent(percent)}
        </span>
      </div>
      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-ink-100">
        <div
          className={cn('h-full rounded-full transition-[width] duration-300', fillClass)}
          style={{ width: `${Math.min(100, percent)}%` }}
        />
      </div>
    </div>
  );
});

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-ink-100 bg-ink-50 px-3 py-2">
      <p className="text-xs text-ink-500">{label}</p>
      <p className="mt-0.5 text-sm font-semibold text-ink-900">{value}</p>
    </div>
  );
}

interface TaskRowProps {
  task: TaskInfo;
  onDelete: (taskId: string) => void;
}

const TaskRow = memo(function TaskRow({ task, onDelete }: TaskRowProps) {
  const tone = STATUS_TONE[task.status];
  const label = STATUS_LABELS[task.status];
  const created = task.created_at ? new Date(task.created_at).toLocaleString() : '—';

  return (
    <tr className="border-t border-ink-100 text-ink-700">
      <td className="max-w-[280px] truncate px-5 py-3 font-medium text-ink-900">
        {task.filename}
      </td>
      <td className="px-5 py-3">
        <span
          className={cn(
            'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium',
            tone,
          )}
        >
          {label}
        </span>
      </td>
      <td className="px-5 py-3 text-ink-500">
        {task.page_count != null ? `${task.page_count} 页` : '—'}
      </td>
      <td className="px-5 py-3 text-ink-500">
        {task.file_size != null ? formatBytes(task.file_size) : '—'}
      </td>
      <td className="px-5 py-3 text-ink-500">
        <span className="inline-flex items-center gap-1">
          <CalendarClock className="h-3 w-3" /> {created}
        </span>
      </td>
      <td className="px-5 py-3">
        <div className="flex items-center justify-end gap-2">
          <Link
            to={`/translate?retranslate=${task.id}`}
            title="用相同设置重新翻译"
          >
            <Button variant="ghost" size="sm">
              重新翻译
            </Button>
          </Link>
          {task.status === 'completed' && task.result_url && (
            <DownloadMenu
              taskId={task.id}
              task={{
                result_url: task.result_url,
                result_mono_url: task.result_mono_url,
                result_md_url: task.result_md_url,
                result_docx_url: task.result_docx_url,
              }}
            />
          )}
          <button
            type="button"
            onClick={() => onDelete(task.id)}
            className="text-ink-400 hover:text-red-500"
            aria-label={`删除 ${task.filename}`}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </td>
    </tr>
  );
});