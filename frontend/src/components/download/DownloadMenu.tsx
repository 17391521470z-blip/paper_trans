import { useCallback, useEffect, useRef, useState } from 'react';
import { Download, FileDown, FileSpreadsheet, FileText } from 'lucide-react';
import { toast } from 'sonner';

import { API_BASE_URL } from '@/lib/constants';
import { useAuthStore } from '@/stores/authStore';
import { cn } from '@/lib/utils';

export type DownloadFormat = 'pdf' | 'dual' | 'mono' | 'monolingual' | 'markdown' | 'docx';

interface DownloadMenuProps {
  taskId: string;
  task?: {
    result_url?: string | null;
    result_mono_url?: string | null;
    result_md_url?: string | null;
    result_docx_url?: string | null;
  };
  variant?: 'ghost' | 'solid';
  size?: 'sm' | 'md';
  label?: string;
  align?: 'left' | 'right';
}

const FORMAT_OPTIONS: Array<{
  format: DownloadFormat;
  label: string;
  hint: string;
  icon: React.ReactNode;
  field: keyof NonNullable<DownloadMenuProps['task']>;
  // HIDDEN-FEATURE: md/docx 暂时禁用,但保留在菜单中作为预告
  disabled?: boolean;
}> = [
  {
    format: 'pdf',
    label: '双语文档 PDF',
    hint: '原文与译文左右对照',
    icon: <FileText className="h-4 w-4" />,
    field: 'result_url',
  },
  {
    format: 'mono',
    label: '纯译文 PDF',
    hint: '仅译文,适合直接阅读',
    icon: <FileDown className="h-4 w-4" />,
    field: 'result_mono_url',
  },
  {
    format: 'docx',
    label: 'Word 文档',
    hint: '即将上线,敬请期待',
    icon: <FileSpreadsheet className="h-4 w-4" />,
    field: 'result_docx_url',
    disabled: true,
  },
  {
    format: 'markdown',
    label: 'Markdown',
    hint: '即将上线,敬请期待',
    icon: <FileDown className="h-4 w-4" />,
    field: 'result_md_url',
    disabled: true,
  },
];

export function DownloadMenu({
  taskId,
  task,
  variant = 'ghost',
  size = 'sm',
  label = '下载',
  align = 'right',
}: DownloadMenuProps) {
  const token = useAuthStore((s) => s.token);
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<DownloadFormat | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleEsc);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleEsc);
    };
  }, [open]);

  const isAvailable = (field: keyof NonNullable<DownloadMenuProps['task']>) =>
    Boolean(task?.[field]);

  const triggerDownload = useCallback(
    async (format: DownloadFormat) => {
      if (pending) return;
      setPending(format);
      try {
        const params = new URLSearchParams({ format });
        if (format === 'mono') {
          // 用 format=pdf + type=mono 下载纯译文 PDF
          params.set('format', 'pdf');
          params.set('type', 'mono');
        } else if (format === 'monolingual') {
          params.set('format', 'pdf');
          params.set('type', 'mono');
        } else if (format === 'dual') {
          params.set('format', 'pdf');
          params.set('type', 'dual');
        }
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
        const ext = format === 'markdown' ? 'md' : 'pdf';
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = `translated-${taskId}.${ext}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);
        toast.success('下载已开始');
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '下载失败');
      } finally {
        setPending(null);
        setOpen(false);
      }
    },
    [pending, taskId, token],
  );

  const sizeClass = size === 'sm' ? 'h-8 px-3 text-xs' : 'h-10 px-4 text-sm';
  const variantClass =
    variant === 'solid'
      ? 'bg-brand-600 text-white hover:bg-brand-700'
      : 'bg-transparent text-ink-700 hover:bg-ink-100 active:bg-ink-200';

  return (
    <div ref={containerRef} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors',
          'focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:ring-offset-white',
          'disabled:cursor-not-allowed disabled:opacity-70',
          sizeClass,
          variantClass,
        )}
      >
        <Download className="h-4 w-4" />
        <span>{label}</span>
      </button>

      {open && (
        <div
          role="menu"
          className={cn(
            'absolute z-50 mt-1 min-w-[220px] overflow-hidden rounded-lg border border-ink-200 bg-white shadow-lg',
            align === 'right' ? 'right-0' : 'left-0',
          )}
        >
          <div className="border-b border-ink-100 px-3 py-2 text-xs text-ink-500">
            选择下载格式
          </div>
          <ul className="py-1">
            {FORMAT_OPTIONS.map((opt) => {
              const available = isAvailable(opt.field);
              const isLoading = pending === opt.format;
              const isDisabled = opt.disabled || !available || Boolean(pending);
              return (
                <li key={opt.format}>
                  <button
                    type="button"
                    disabled={isDisabled}
                    onClick={() => {
                      if (opt.disabled) {
                        toast.info('该格式即将上线,敬请期待。');
                        return;
                      }
                      triggerDownload(opt.format);
                    }}
                    className={cn(
                      'flex w-full items-center gap-3 px-3 py-2 text-left text-sm transition-colors',
                      !isDisabled
                        ? 'text-ink-700 hover:bg-brand-50 hover:text-brand-700'
                        : 'cursor-not-allowed text-ink-300',
                    )}
                  >
                    <span className={cn(!isDisabled ? 'text-brand-600' : 'text-ink-300')}>
                      {isLoading ? (
                        <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                      ) : (
                        opt.icon
                      )}
                    </span>
                    <span className="flex-1">
                      <span className="block font-medium">{opt.label}</span>
                      <span className="block text-[11px] text-ink-400">{opt.hint}</span>
                    </span>
                    {opt.disabled ? (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
                        敬请期待
                      </span>
                    ) : !available ? (
                      <span className="text-[11px] text-ink-300">未生成</span>
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
