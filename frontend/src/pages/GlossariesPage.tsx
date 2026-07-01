import { memo, useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  Download,
  Edit3,
  FileSpreadsheet,
  Library,
  Lock,
  Plus,
  Search,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { toast } from 'sonner';

import { PageTitle } from '../components/seo/PageTitle';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Spinner } from '@/components/ui/Spinner';
import { cn, formatNumber } from '@/lib/utils';
import { useGlossaryStore, type Glossary } from '@/stores/glossaryStore';
import { useAuthStore } from '@/stores/authStore';
import { getErrorMessage } from '@/lib/errorHandler';
import { API_BASE_URL } from '@/lib/constants';

const MAX_CSV_BYTES = 5 * 1024 * 1024;

export function GlossariesPage() {
  const user = useAuthStore((s) => s.user);
  const list = useGlossaryStore((s) => s.list);
  const isLoading = useGlossaryStore((s) => s.isLoading);
  const fetchList = useGlossaryStore((s) => s.fetchList);
  const upload = useGlossaryStore((s) => s.upload);
  const remove = useGlossaryStore((s) => s.remove);

  const [showUpload, setShowUpload] = useState(false);
  const [search, setSearch] = useState('');

  useEffect(() => {
    void fetchList();
  }, [fetchList]);

  const filtered = list.filter((g) =>
    g.name.toLowerCase().includes(search.trim().toLowerCase()),
  );

  const tier = (user?.plan ?? 'free').toLowerCase();
  const isFree = tier === 'free';
  const limit = isFree ? 1 : tier === 'standard' ? 5 : 20;
  const used = list.filter((g) => !g.is_builtin).length;
  const remaining = Math.max(0, limit - used);

  const handleDelete = useCallback(
    async (id: string) => {
      if (!confirm('确定要删除这个术语库吗？该操作不可撤销。')) return;
      try {
        await remove(id);
        toast.success('术语库已删除');
      } catch (err) {
        toast.error(getErrorMessage(err));
      }
    },
    [remove],
  );

  const token = useAuthStore((s) => s.token);

  const handleExport = useCallback(
    async (glossary: Glossary) => {
      try {
        const resp = await fetch(
          `${API_BASE_URL}/glossaries/${glossary.id}/export`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (!resp.ok) {
          const body = await resp.text().catch(() => '');
          throw new Error(body || `HTTP ${resp.status}`);
        }
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${glossary.name}-export.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        toast.success(`已导出 ${glossary.name}`);
      } catch (err) {
        toast.error(getErrorMessage(err));
      }
    },
    [token],
  );

  return (
    <div className="container-page space-y-8 py-10 lg:py-12">
      <PageTitle title="术语库管理" />
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-ink-900">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
              <Library className="h-5 w-5" />
            </span>
            术语库管理
          </h1>
          <p className="mt-1 text-sm text-ink-500">
            通过自定义术语库,确保同一领域的术语在所有翻译中保持一致。
          </p>
          <p className="mt-1 text-xs text-ink-400">单个术语库最多 1,000 条。</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-ink-500">
            已使用 {used} / {limit} 个
          </span>
          <Button
            onClick={() => setShowUpload(true)}
            leftIcon={<Plus className="h-4 w-4" />}
            disabled={isFree && used >= limit}
          >
            新建术语库
          </Button>
        </div>
      </header>

      {isFree && (
        <Card className="flex flex-col items-start gap-3 border-amber-200 bg-amber-50 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-amber-100 text-amber-700">
              <Lock className="h-4 w-4" />
            </span>
            <div>
              <h2 className="text-sm font-semibold text-ink-900">免费档仅支持 1 个自定义术语库</h2>
              <p className="mt-1 text-xs text-ink-500">
                升级到标准档（29 元 / 月）可解锁 5 个术语库、200 页月配额。
              </p>
            </div>
          </div>
          <Button size="sm" variant="secondary">
            查看套餐
          </Button>
        </Card>
      )}

      <Card padding="none">
        <div className="flex flex-col gap-2 border-b border-ink-100 px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="max-w-sm">
            <Input
              placeholder="搜索术语库名称…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              leftIcon={<Search className="h-4 w-4" />}
            />
          </div>
          <span className="text-xs text-ink-500">共 {filtered.length} 个术语库</span>
        </div>

        {isLoading && list.length === 0 ? (
          <div className="flex items-center justify-center py-12">
            <Spinner label="正在加载术语库…" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <FileSpreadsheet className="mx-auto h-10 w-10 text-ink-300" aria-hidden="true" />
            <p className="mt-3 text-sm font-medium text-ink-900">
              {search ? '没有匹配的术语库' : '还没有任何术语库'}
            </p>
            <p className="mt-1 text-xs text-ink-500">
              点击右上方「新建术语库」上传 CSV 文件即可创建。
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="bg-ink-50 text-ink-600">
                <tr>
                  <th className="px-5 py-3 font-medium">名称</th>
                  <th className="px-5 py-3 font-medium">领域</th>
                  <th className="px-5 py-3 font-medium">词条数</th>
                  <th className="px-5 py-3 font-medium">更新时间</th>
                  <th className="px-5 py-3 font-medium text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((g) => (
                  <GlossaryRow
                    key={g.id}
                    glossary={g}
                    onDelete={handleDelete}
                    onExport={handleExport}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onUpload={async (file, name, description) => {
            try {
              await upload(file, name, description);
              toast.success('术语库已创建');
              setShowUpload(false);
            } catch (err) {
              toast.error(getErrorMessage(err));
            }
          }}
          remaining={remaining}
          isFree={isFree}
        />
      )}
    </div>
  );
}

interface GlossaryRowProps {
  glossary: Glossary;
  onDelete: (id: string) => void;
  onExport: (glossary: Glossary) => void;
}

const GlossaryRow = memo(function GlossaryRow({
  glossary,
  onDelete,
  onExport,
}: GlossaryRowProps) {
  const updated = glossary.updated_at ? new Date(glossary.updated_at).toLocaleString() : '—';
  return (
    <tr className="border-t border-ink-100 text-ink-700">
      <td className="px-5 py-3">
        <div className="flex items-center gap-2">
          {glossary.is_builtin ? (
            <Lock className="h-3.5 w-3.5 text-ink-400" />
          ) : (
            <FileSpreadsheet className="h-3.5 w-3.5 text-brand-600" />
          )}
          <span className="font-medium text-ink-900">{glossary.name}</span>
        </div>
        {glossary.description && (
          <p className="ml-5 mt-0.5 line-clamp-1 text-xs text-ink-500">
            {glossary.description}
          </p>
        )}
      </td>
      <td className="px-5 py-3 text-ink-500">{glossary.domain ?? '通用'}</td>
      <td className="px-5 py-3 text-ink-500">{formatNumber(glossary.term_count)}</td>
      <td className="px-5 py-3 text-ink-500">{updated}</td>
      <td className="px-5 py-3">
        <div className="flex items-center justify-end gap-1">
          <button
            type="button"
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-ink-500 hover:bg-ink-100"
            aria-label="编辑术语库"
          >
            <Edit3 className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => onExport(glossary)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-ink-500 hover:bg-ink-100"
            aria-label="导出 CSV"
          >
            <Download className="h-4 w-4" />
          </button>
          {!glossary.is_builtin && (
            <button
              type="button"
              onClick={() => onDelete(glossary.id)}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md text-ink-400 hover:bg-red-50 hover:text-red-600"
              aria-label="删除术语库"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
        </div>
      </td>
    </tr>
  );
});

interface UploadModalProps {
  onClose: () => void;
  onUpload: (file: File, name: string, description: string) => Promise<void>;
  remaining: number;
  isFree: boolean;
}

function UploadModal({ onClose, onUpload, remaining, isFree }: UploadModalProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const next = e.target.files?.[0] ?? null;
    setError(null);
    if (!next) {
      setFile(null);
      return;
    }
    if (!/\.csv$/i.test(next.name)) {
      setError('仅支持 .csv 文件');
      setFile(null);
      return;
    }
    if (next.size > MAX_CSV_BYTES) {
      setError(`文件超过 5MB 上限（当前 ${(next.size / 1024 / 1024).toFixed(2)}MB）`);
      setFile(null);
      return;
    }
    setFile(next);
    if (!name) {
      setName(next.name.replace(/\.csv$/i, ''));
    }
  }, [name]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);
      if (!file) {
        setError('请选择 CSV 文件');
        return;
      }
      if (!name.trim()) {
        setError('请输入术语库名称');
        return;
      }
      if (isFree && remaining <= 0) {
        setError('免费档术语库额度已满，请升级套餐');
        return;
      }
      setSubmitting(true);
      try {
        await onUpload(file, name.trim(), description.trim());
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setSubmitting(false);
      }
    },
    [description, file, isFree, name, onUpload, remaining],
  );

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 px-4"
    >
      <Card className="w-full max-w-lg p-6">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-ink-900">新建术语库</h2>
            <p className="mt-1 text-xs text-ink-500">
              CSV 第一列原文，第二列译文，第三列可选上下文。最大 5MB。
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

        <form onSubmit={handleSubmit} className="space-y-4">
          <label
            className={cn(
              'flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed bg-white px-4 py-8 text-center transition-colors',
              file ? 'border-brand-300 bg-brand-50' : 'border-ink-200 hover:border-brand-300',
            )}
          >
            <Upload className="h-5 w-5 text-brand-600" />
            <span className="text-sm font-medium text-ink-900">
              {file ? file.name : '点击选择 CSV 文件'}
            </span>
            <span className="text-xs text-ink-500">
              {file
                ? `${(file.size / 1024).toFixed(1)} KB`
                : '支持 ≤ 5MB,UTF-8 编码,单个文件最多 1,000 条'}
            </span>
            <input
              ref={inputRef}
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              onChange={handleFileChange}
            />
          </label>

          <Input
            label="术语库名称"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="如：CV 方向 · 视觉 Transformer"
            required
            disabled={submitting}
          />
          <Input
            label="描述（可选）"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="说明该术语库的领域与使用场景"
            disabled={submitting}
          />

          {error && (
            <p
              role="alert"
              className="flex items-center gap-1.5 text-xs text-red-600"
            >
              <AlertCircle className="h-3.5 w-3.5" />
              {error}
            </p>
          )}

          <div className="flex items-center justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={submitting}
            >
              取消
            </Button>
            <Button
              type="submit"
              isLoading={submitting}
              disabled={submitting}
              leftIcon={<Upload className="h-4 w-4" />}
            >
              上传并创建
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}