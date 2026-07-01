import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Download,
  FileDown,
  FileSpreadsheet,
  FileText,
  History,
  Languages,
  Play,
  RotateCcw,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';

import { PageTitle } from '../components/seo/PageTitle';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { PdfDropzone, type PdfInfo } from '@/components/upload/PdfDropzone';
import { cn, formatBytes, formatPercent } from '@/lib/utils';
import {
  API_BASE_URL,
  SUPPORTED_LANGUAGES,
  type PlanCode,
} from '@/lib/constants';
import { useAuthStore } from '@/stores/authStore';
import { useQuotaStore } from '@/stores/quotaStore';
import { useTaskStore, type TaskInfo, type TaskStatus } from '@/stores/taskStore';
import { useGlossaryStore } from '@/stores/glossaryStore';
import { subscribeTaskProgress, type WsEvent } from '@/lib/ws';
import { getErrorMessage, isQuotaError } from '@/lib/errorHandler';
import { apiGet } from '@/lib/api';

const SERVICE_OPTIONS = [
  { code: 'deepseek', model: 'deepseek-chat', label: 'DeepSeek-V3', description: '推荐 · 性价比高' },
  { code: 'glm', model: 'glm-4-flash', label: 'GLM-4-Flash', description: '备选 · 速度更快' },
  { code: 'openai', model: 'gpt-4o-mini', label: 'GPT-4o-mini', description: '兼容 OpenAI 协议' },
] as const;

const LANGUAGE_OPTIONS = SUPPORTED_LANGUAGES.map((l) => ({
  value: l.code,
  label: l.label,
}));

const LANGUAGE_OPTIONS_NO_AUTO = LANGUAGE_OPTIONS.filter((l) => l.value !== 'auto');

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

// 最近任务最多展示数量
// 估算:每行约 60-70px(含 padding)+ 标题区约 64px
// 左侧表单 card 在 lg 屏幕高度约 700-900px,ProgressPanel 完成态约 380px,
// 剩余约 320-520px → 取 5 条,既能让右侧卡片底缘接近左侧,又不让卡片过高
const RECENT_TASKS_MAX = 5;

export function TranslatePage() {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const quota = useQuotaStore((s) => s.quota);
  const refreshQuota = useQuotaStore((s) => s.refresh);

  const taskStore = useTaskStore();
  const {
    currentTask,
    status,
    progress,
    errorMessage,
    isSubmitting,
    uploadProgress,
    recentTasks,
    fetchRecentTasks,
  } = taskStore;

  const glossaries = useGlossaryStore((s) => s.list);
  const fetchGlossaries = useGlossaryStore((s) => s.fetchList);

  const [searchParams, setSearchParams] = useSearchParams();
  const retranslateTaskId = searchParams.get('retranslate');

  const [file, setFile] = useState<File | null>(null);
  const [pdfInfo, setPdfInfo] = useState<PdfInfo | null>(null);
  const [sourceLang, setSourceLang] = useState<string>('en');
  const [targetLang, setTargetLang] = useState<string>('zh');
  const [glossaryId, setGlossaryId] = useState<string>('');

  const unsubscribeRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    void refreshQuota();
    void fetchGlossaries();
    void fetchRecentTasks(1, 4);
  }, [fetchGlossaries, fetchRecentTasks, refreshQuota]);

  // 处理 ?retranslate=<task_id> 参数:拉取历史任务设置项预填表单,
  // 让用户用相同配置(语言/术语库)重新上传同一文件再翻译。
  // 注意:用 apiGet 直接拉,不调 taskStore.fetchTask——那个会覆盖 currentTask
  useEffect(() => {
    if (!retranslateTaskId) return;
    let cancelled = false;
    (async () => {
      try {
        const task = await apiGet<TaskInfo>(`/tasks/${retranslateTaskId}`);
        if (cancelled || !task) return;
        if (task.source_language) setSourceLang(task.source_language);
        if (task.target_language) setTargetLang(task.target_language);
        // llm_service 不再暴露给用户选择，但仍记录历史值供后端使用
        if (task.glossary_id) {
          setGlossaryId(String(task.glossary_id));
        }
        toast.info('已按历史任务预填设置,请重新上传同一 PDF');
      } catch {
        toast.error('历史任务信息加载失败');
      } finally {
        // 清掉 query 避免刷新再次触发
        setSearchParams({}, { replace: true });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [retranslateTaskId, setSearchParams]);

  useEffect(() => {
    return () => {
      unsubscribeRef.current?.();
      unsubscribeRef.current = null;
    };
  }, []);

  // llm_service 固定为默认模型，隐藏用户选择面板
  const activeService = SERVICE_OPTIONS[0];

  const handleFileChange = useCallback((next: File | null, info?: PdfInfo) => {
    setFile(next);
    setPdfInfo(info ?? null);
  }, []);

  const handleRetry = useCallback(async () => {
    if (!file) return;
    taskStore.reset();
    try {
      await taskStore.submitTask(
        {
          file,
          sourceLang,
          targetLang,
          service: activeService.code,
          model: activeService.model,
          glossaryId: glossaryId || null,
        },
        () => {
          /* upload progress is tracked in store */
        },
      );
      const id = useTaskStore.getState().currentTask?.id;
      if (id) {
        subscribeToTask(id);
      }
      await refreshQuota();
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  }, [activeService.code, activeService.model, file, glossaryId, refreshQuota, sourceLang, targetLang, taskStore]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!file) {
        toast.error('请先上传 PDF 文件');
        return;
      }
      if (quota && quota.remaining_pages <= 0) {
        toast.error('本月翻译配额已用完，请升级套餐或等待下月。');
        return;
      }
      taskStore.reset();
      try {
        await taskStore.submitTask(
          {
            file,
            sourceLang,
            targetLang,
            service: activeService.code,
            model: activeService.model,
            glossaryId: glossaryId || null,
          },
          () => {
            /* progress tracked in store */
          },
        );
        const id = useTaskStore.getState().currentTask?.id;
        if (id) subscribeToTask(id);
        await refreshQuota();
      } catch (err) {
        if (isQuotaError(err)) {
          toast.error('本月翻译配额已用完，请升级套餐或等待下月。');
        } else {
          toast.error(getErrorMessage(err));
        }
      }
    },
    [activeService.code, activeService.model, file, glossaryId, quota, refreshQuota, sourceLang, targetLang, taskStore],
  );

  const subscribeToTask = useCallback(
    (taskId: string) => {
      unsubscribeRef.current?.();
      unsubscribeRef.current = subscribeTaskProgress(
        taskId,
        token,
        (event: WsEvent) => {
          if (typeof event.progress === 'number') {
            taskStore.updateProgress(event.progress, 'processing');
          }
          if (event.type === 'completed') {
            taskStore.updateProgress(100, 'completed');
            void taskStore.fetchTask(taskId).then(() => {
              toast.success('翻译完成，可下载结果');
              void fetchRecentTasks(1, 4);
              void refreshQuota();
            });
          }
          if (event.type === 'failed') {
            taskStore.setError(event.error ?? '翻译失败，请重试');
            toast.error(event.error ?? '翻译失败，请重试');
          }
        },
        {
          maxRetries: 3,
          onRetry: (attempt) => {
            toast.info(`连接中断，正在第 ${attempt} 次重试…`, { duration: 2500 });
          },
          onClose: (code) => {
            if (code !== 1000) {
              // abnormal close
            }
          },
        },
      );
    },
    [fetchRecentTasks, refreshQuota, taskStore, token],
  );

  const handleRemoveRecent = useCallback(
    async (taskId: string) => {
      try {
        await taskStore.deleteTask(taskId);
        toast.success('已删除该任务');
      } catch (err) {
        toast.error(getErrorMessage(err));
      }
    },
    [taskStore],
  );

  const handleStartNew = useCallback(() => {
    taskStore.reset();
    setFile(null);
    setPdfInfo(null);
    unsubscribeRef.current?.();
    unsubscribeRef.current = null;
  }, [taskStore]);

  const isBusy = isSubmitting || status === 'uploading' || status === 'pending' || status === 'processing';

  return (
    <div className="container-page py-10 lg:py-12">
      <PageTitle title="翻译论文" />
      <header className="mb-8 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink-900">
            翻译工作台
          </h1>
          <p className="mt-1 text-sm text-ink-500">
            上传 PDF，设置翻译选项，实时查看进度并下载结果。
          </p>
        </div>
        <QuotaBadge
          tier={user?.plan ?? quota?.tier}
          remaining={quota?.remaining_pages}
          monthly={quota?.monthly_pages}
        />
      </header>

      <div className="grid items-stretch gap-6 lg:grid-cols-5">
        <Card className="flex flex-col lg:col-span-3" padding="lg">
          <form className="flex flex-1 flex-col space-y-6" onSubmit={handleSubmit}>
            <PdfDropzone
              value={file}
              onChange={handleFileChange}
              uploadProgress={uploadProgress}
              uploadStatus={isSubmitting ? 'uploading' : file ? 'success' : 'idle'}
            />

            <div className="grid gap-4 sm:grid-cols-2">
              <SelectField
                label="源语言"
                value={sourceLang}
                onChange={setSourceLang}
                options={LANGUAGE_OPTIONS_NO_AUTO}
                disabled={isBusy}
              />
              <SelectField
                label="目标语言"
                value={targetLang}
                onChange={setTargetLang}
                options={LANGUAGE_OPTIONS}
                disabled={isBusy}
              />
            </div>

            <SelectField
              label="术语库（可选）"
              value={glossaryId}
              onChange={setGlossaryId}
              placeholder="不使用术语库"
              options={glossaries.map((g) => ({
                value: g.id,
                label: `${g.name} · ${g.term_count} 词条`,
              }))}
              disabled={isBusy}
              hint={
                <Link to="/glossaries" className="text-link">
                  管理术语库 →
                </Link>
              }
            />

            <div className="flex flex-col-reverse items-stretch gap-3 border-t border-ink-100 pt-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-ink-500">
                {file
                  ? `已选择：${file.name} · ${formatBytes(file.size)}${
                      pdfInfo?.pages ? ` · ${pdfInfo.pages} 页` : ''
                    }`
                  : '支持单文件 ≤ 50MB、≤ 100 页的 PDF'}
              </p>
              <div className="flex items-center gap-2">
                {(status === 'completed' || status === 'failed') && (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={handleStartNew}
                    leftIcon={<RotateCcw className="h-4 w-4" />}
                  >
                    重新开始
                  </Button>
                )}
                <Button
                  type="submit"
                  isLoading={isSubmitting}
                  disabled={isBusy || !file}
                  leftIcon={!isBusy ? <Play className="h-4 w-4" /> : undefined}
                >
                  {isSubmitting ? '正在提交…' : '开始翻译'}
                </Button>
              </div>
            </div>
          </form>
        </Card>

        <div className="flex flex-col gap-6 lg:col-span-2">
          <ProgressPanel
            status={status}
            progress={progress}
            errorMessage={errorMessage}
            task={currentTask}
            onRetry={handleRetry}
            onStartNew={handleStartNew}
          />

          <Card padding="none" className="flex flex-1 flex-col">
            <div className="border-b border-ink-100 px-5 py-4">
              <CardHeader
                title={
                  <span className="flex items-center gap-2 text-sm font-semibold text-ink-900">
                    <History className="h-4 w-4 text-brand-600" />
                    最近任务
                  </span>
                }
                description={`最多展示最近 ${RECENT_TASKS_MAX} 条翻译记录`}
              />
            </div>
            {recentTasks.length === 0 ? (
              <p className="flex flex-1 items-center justify-center px-5 py-6 text-sm text-ink-500">
                暂无历史任务
              </p>
            ) : (
              <ul className="divide-y divide-ink-100">
                {recentTasks.slice(0, RECENT_TASKS_MAX).map((task) => (
                  <RecentTaskRow
                    key={task.id}
                    task={task}
                    onRemove={handleRemoveRecent}
                  />
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

interface SelectFieldProps<T extends string> {
  label: string;
  value: T | '';
  onChange: (value: T) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
  disabled?: boolean;
  hint?: React.ReactNode;
}

function SelectField<T extends string>({
  label,
  value,
  onChange,
  options,
  placeholder,
  disabled,
  hint,
}: SelectFieldProps<T>) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-ink-700">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        disabled={disabled}
        className={cn(
          'h-10 w-full rounded-lg border border-ink-200 bg-white px-3 text-sm text-ink-900',
          'focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30',
          disabled && 'cursor-not-allowed bg-ink-50 text-ink-400',
        )}
      >
        {placeholder && (
          <option value="">{placeholder}</option>
        )}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {hint && <span className="text-xs text-ink-500">{hint}</span>}
    </label>
  );
}

interface ProgressPanelProps {
  status: TaskStatus;
  progress: number;
  errorMessage: string | null;
  task: TaskInfo | null;
  onRetry: () => void;
  onStartNew: () => void;
}

const ProgressPanel = memo(function ProgressPanel({
  status,
  progress,
  errorMessage,
  task,
  onRetry,
  onStartNew,
}: ProgressPanelProps) {
  if (status === 'idle' && !task) {
    return (
      <Card className="flex flex-col items-center justify-center gap-3 py-10 text-center">
        <span className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-700">
          <Sparkles className="h-6 w-6" />
        </span>
        <h3 className="text-base font-semibold text-ink-900">等待你的论文</h3>
        <p className="max-w-xs text-sm text-ink-500">
          上传 PDF 后点击「开始翻译」，我们会自动调用术语库完成翻译。
        </p>
      </Card>
    );
  }

  const statusLabel = STATUS_LABELS[status];
  const tone = STATUS_TONE[status];
  const isWorking = status === 'uploading' || status === 'pending' || status === 'processing';

  return (
    <Card padding="lg">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-ink-900">翻译状态</h3>
        <span
          className={cn(
            'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium',
            tone,
          )}
        >
          {isWorking && <Spinner size="sm" className="mr-1" />}
          {statusLabel}
        </span>
      </div>

      <div className="mt-4">
        <div className="mb-2 flex items-center justify-between text-xs text-ink-500">
          <span>{task?.filename ?? '当前任务'}</span>
          <span>{formatPercent(progress)}</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-ink-100">
          <div
            className={cn(
              'h-full rounded-full transition-[width] duration-300',
              status === 'completed'
                ? 'bg-emerald-500'
                : status === 'failed'
                  ? 'bg-red-500'
                  : 'bg-brand-600',
            )}
            style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
          />
        </div>
      </div>

      {status === 'failed' && (
        <div
          role="alert"
          className="mt-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <div className="flex-1">
            <p className="font-medium">翻译失败</p>
            <p className="mt-0.5 text-xs text-red-600">
              {errorMessage ?? '请稍后再试或更换文件。'}
            </p>
            <div className="mt-2 flex gap-2">
              <Button size="sm" onClick={onRetry} leftIcon={<RotateCcw className="h-3.5 w-3.5" />}>
                重试
              </Button>
              <Button size="sm" variant="ghost" onClick={onStartNew}>
                新建任务
              </Button>
            </div>
          </div>
        </div>
      )}

      {status === 'completed' && task && (
        <div className="mt-4 space-y-3">
          <p className="flex items-center gap-2 text-sm text-emerald-700">
            <CheckCircle2 className="h-4 w-4" />
            已完成
            {task.page_count != null && ` · ${task.page_count} 页`}
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <DownloadLink
              taskId={task.id}
              format="pdf"
              label="双语文档 PDF"
              icon={<FileText className="h-4 w-4" />}
            />
            <DownloadLink
              taskId={task.id}
              format="pdf"
              type="mono"
              label="纯译文 PDF"
              icon={<FileDown className="h-4 w-4" />}
            />
            <DownloadLink
              taskId={task.id}
              format="markdown"
              label="Markdown"
              icon={<FileSpreadsheet className="h-4 w-4" />}
              disabled
              comingSoonHint="即将上线,敬请期待"
            />
            <DownloadLink
              taskId={task.id}
              format="docx"
              label="Word 文档"
              icon={<FileSpreadsheet className="h-4 w-4" />}
              disabled
              comingSoonHint="即将上线,敬请期待"
            />
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onStartNew}
            leftIcon={<RotateCcw className="h-3.5 w-3.5" />}
          >
            开始新任务
          </Button>
        </div>
      )}

      {isWorking && (
        <p className="mt-3 text-xs text-ink-500">
          翻译通常需要 30 秒到 3 分钟，取决于页数与模型响应速度。请保持页面打开。
        </p>
      )}
    </Card>
  );
});

interface DownloadLinkProps {
  taskId: string;
  format: 'pdf' | 'markdown' | 'docx' | 'monolingual';
  type?: 'dual' | 'mono';
  label: string;
  icon: React.ReactNode;
  // HIDDEN-FEATURE: 禁用某个下载格式(灰显且 toast 提示)
  disabled?: boolean;
  comingSoonHint?: string;
}

function DownloadLink({ taskId, format, type, label, icon, disabled, comingSoonHint }: DownloadLinkProps) {
  const token = useAuthStore((s) => s.token);
  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownload = useCallback(async () => {
    if (disabled) {
      toast.info(comingSoonHint ?? '该格式即将上线,敬请期待。');
      return;
    }
    if (isDownloading) return;
    setIsDownloading(true);
    try {
      const params = new URLSearchParams({ format });
      if (type) params.set('type', type);
      const resp = await fetch(
        `${API_BASE_URL}/tasks/${taskId}/download?${params.toString()}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!resp.ok) {
        const body = await resp.text().catch(() => '');
        throw new Error(body || `HTTP ${resp.status}`);
      }
      const blob = await resp.blob();
      const blobUrl = URL.createObjectURL(blob);
      const ext = format === 'markdown' ? 'md' : format;
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `translated-${taskId}.${ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '下载失败');
    } finally {
      setIsDownloading(false);
    }
  }, [comingSoonHint, disabled, format, isDownloading, taskId, token, type]);

  return (
    <button
      type="button"
      onClick={handleDownload}
      disabled={disabled || isDownloading}
      title={disabled ? comingSoonHint : undefined}
      className="inline-flex items-center gap-2 rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm font-medium text-ink-700 transition-colors hover:border-brand-300 hover:bg-brand-50 disabled:opacity-60"
    >
      <span className="text-brand-600">{icon}</span>
      <span className="flex-1 text-left">
        {disabled ? '敬请期待' : isDownloading ? '下载中…' : label}
      </span>
      {disabled ? (
        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
          即将上线
        </span>
      ) : (
        <Download className="ml-auto h-4 w-4 text-ink-400" />
      )}
    </button>
  );
}

interface RecentTaskRowProps {
  task: TaskInfo;
  onRemove: (taskId: string) => void;
}

const RecentTaskRow = memo(function RecentTaskRow({
  task,
  onRemove,
}: RecentTaskRowProps) {
  const tone = STATUS_TONE[task.status];
  const label = STATUS_LABELS[task.status];
  const created = task.created_at ? new Date(task.created_at).toLocaleString() : '';

  return (
    <li className="flex items-center gap-3 px-5 py-3">
      <div className="flex flex-1 flex-col gap-0.5 truncate">
        <p className="truncate text-sm font-medium text-ink-900">{task.filename}</p>
        <p className="flex items-center gap-2 text-xs text-ink-500">
          <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-medium', tone)}>
            {label}
          </span>
          {task.page_count != null && <span>{task.page_count} 页</span>}
          {created && (
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3 w-3" /> {created}
            </span>
          )}
        </p>
      </div>
      {task.status === 'completed' && task.result_url && (
        <Link
          to={`/dashboard?task=${task.id}`}
          className="text-link text-xs"
        >
          <ArrowRight className="mr-1 inline h-3 w-3" />
          查看
        </Link>
      )}
      <button
        type="button"
        onClick={() => onRemove(task.id)}
        className="text-ink-400 hover:text-red-500"
        aria-label={`删除 ${task.filename}`}
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </li>
  );
});

interface QuotaBadgeProps {
  tier?: PlanCode | string | null;
  remaining?: number;
  monthly?: number;
}

const QuotaBadge = memo(function QuotaBadge({
  tier,
  remaining,
  monthly,
}: QuotaBadgeProps) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-ink-200 bg-white px-4 py-2 shadow-card">
      <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
        <Languages className="h-4 w-4" />
      </span>
      <div className="text-xs">
        <p className="font-medium text-ink-900">
          套餐：{tier ? tier.toUpperCase() : 'FREE'}
        </p>
        <p className="text-ink-500">
          本月剩余 {remaining ?? '—'} / {monthly ?? '—'} 页
        </p>
      </div>
      <Link to="/billing" className="text-link ml-2 text-xs">
        升级
      </Link>
    </div>
  );
});