import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useDropzone, type FileRejection } from 'react-dropzone';
import { AlertCircle, CheckCircle2, FileText, Upload, X } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { cn } from '@/lib/utils';
import { formatBytes } from '@/lib/utils';
import { ACCEPTED_PDF_MIME, FILE_LIMITS } from '@/lib/constants';
import { getPdfPageCount } from '@/lib/pdfWorker';

export interface PdfDropzoneProps {
  value?: File | null;
  onChange?: (file: File | null, info?: PdfInfo) => void;
  maxBytes?: number;
  maxPages?: number;
  disabled?: boolean;
  uploadProgress?: number;
  uploadStatus?: 'idle' | 'uploading' | 'success' | 'error';
  errorMessage?: string;
  className?: string;
  description?: string;
}

export interface PdfInfo {
  name: string;
  size: number;
  pages?: number;
}

const DEFAULT_DESCRIPTION = `支持单文件 ≤ ${FILE_LIMITS.maxPages} 页、≤ ${formatBytes(FILE_LIMITS.maxBytes)} 的 PDF`;

export function PdfDropzone({
  value,
  onChange,
  maxBytes = FILE_LIMITS.maxBytes,
  maxPages = FILE_LIMITS.maxPages,
  disabled = false,
  uploadProgress = 0,
  uploadStatus = 'idle',
  errorMessage,
  className,
  description = DEFAULT_DESCRIPTION,
}: PdfDropzoneProps) {
  const [validationError, setValidationError] = useState<string | null>(null);
  const [pageCount, setPageCount] = useState<number | null>(null);
  const [isReadingPages, setIsReadingPages] = useState(false);
  const lastValidatedFileRef = useRef<File | null>(null);

  useEffect(() => {
    if (!value) {
      setPageCount(null);
      setValidationError(null);
      lastValidatedFileRef.current = null;
      return;
    }
    if (lastValidatedFileRef.current === value) return;
    lastValidatedFileRef.current = value;
    setValidationError(null);
    setIsReadingPages(true);
    let cancelled = false;
    getPdfPageCount(value)
      .then((pages) => {
        if (cancelled) return;
        if (pages > maxPages) {
          setValidationError(
            `PDF 共 ${pages} 页，超过 ${maxPages} 页上限。请精简后重新上传。`,
          );
          setPageCount(pages);
        } else {
          setPageCount(pages);
        }
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setValidationError(err.message);
      })
      .finally(() => {
        if (!cancelled) setIsReadingPages(false);
      });
    return () => {
      cancelled = true;
    };
  }, [value, maxPages]);

  const handleDrop = useCallback(
    (accepted: File[], rejections: FileRejection[]) => {
      setValidationError(null);
      if (rejections.length > 0) {
        const reasons = rejections[0]?.errors
          .map((e) => {
            if (e.code === 'file-too-large') return `文件超过 ${formatBytes(maxBytes)}`;
            if (e.code === 'file-invalid-type') return '仅支持 PDF 文件';
            return e.message;
          })
          .join('；');
        setValidationError(reasons || '文件校验失败');
        onChange?.(null);
        return;
      }
      const file = accepted[0];
      if (!file) return;
      if (file.size > maxBytes) {
        setValidationError(`文件超过 ${formatBytes(maxBytes)} 上限`);
        onChange?.(null);
        return;
      }
      onChange?.(file);
    },
    [maxBytes, onChange],
  );

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop: handleDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxSize: maxBytes,
    maxFiles: 1,
    disabled: disabled || uploadStatus === 'uploading',
    noClick: true,
    noKeyboard: true,
  });

  const handleRemove = useCallback(() => {
    onChange?.(null);
    setPageCount(null);
    setValidationError(null);
    lastValidatedFileRef.current = null;
  }, [onChange]);

  const displayError = validationError || errorMessage || null;
  const isUploading = uploadStatus === 'uploading';
  const isSuccess = uploadStatus === 'success' && !!value;

  const fileLabel = useMemo(() => {
    if (!value) return null;
    const size = formatBytes(value.size);
    if (pageCount !== null) return `${value.name} · ${size} · ${pageCount} 页`;
    return `${value.name} · ${size}`;
  }, [value, pageCount]);

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <div
        {...getRootProps()}
        className={cn(
          'relative flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed bg-white px-6 py-10 text-center transition-colors',
          isDragActive
            ? 'border-brand-500 bg-brand-50'
            : 'border-ink-200 hover:border-brand-400 hover:bg-ink-50',
          (disabled || isUploading) && 'pointer-events-none opacity-60',
          displayError && 'border-red-300 bg-red-50/50',
        )}
        role="button"
        tabIndex={0}
        aria-label="拖拽或上传 PDF 文件"
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            open();
          }
        }}
      >
        <input {...getInputProps()} aria-label="选择 PDF 文件" />

        {value ? (
          <div className="flex w-full flex-col items-center gap-3">
            <span
              className={cn(
                'inline-flex h-12 w-12 items-center justify-center rounded-full',
                isSuccess
                  ? 'bg-brand-100 text-brand-700'
                  : displayError
                    ? 'bg-red-100 text-red-600'
                    : 'bg-brand-50 text-brand-700',
              )}
            >
              {isSuccess ? (
                <CheckCircle2 className="h-6 w-6" />
              ) : (
                <FileText className="h-6 w-6" />
              )}
            </span>
            <p className="max-w-full truncate text-sm font-medium text-ink-900">
              {fileLabel}
            </p>
            {isReadingPages ? (
              <Spinner size="sm" label="正在读取 PDF 页数…" />
            ) : isUploading ? (
              <div className="w-full max-w-xs space-y-1.5">
                <div className="h-2 w-full overflow-hidden rounded-full bg-ink-100">
                  <div
                    className="h-full rounded-full bg-brand-600 transition-[width] duration-200"
                    style={{ width: `${Math.min(100, uploadProgress)}%` }}
                  />
                </div>
                <p className="text-xs text-ink-500">
                  上传中 {Math.min(100, Math.round(uploadProgress))}%
                </p>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={(e) => {
                    e.stopPropagation();
                    open();
                  }}
                >
                  重新选择
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRemove();
                  }}
                  leftIcon={<X className="h-4 w-4" />}
                >
                  移除
                </Button>
              </div>
            )}
          </div>
        ) : (
          <>
            <span className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-700">
              <Upload className="h-6 w-6" />
            </span>
            <div className="space-y-1">
              <p className="text-sm font-medium text-ink-900">
                {isDragActive ? '松开鼠标即可上传' : '拖拽 PDF 到此，或点击下方按钮'}
              </p>
              <p className="text-xs text-ink-500">{description}</p>
            </div>
            <Button
              type="button"
              size="md"
              variant="primary"
              onClick={(e) => {
                e.stopPropagation();
                open();
              }}
            >
              选择文件
            </Button>
          </>
        )}
      </div>

      {displayError && (
        <p
          role="alert"
          className="flex items-start gap-1.5 text-xs text-red-600"
        >
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>{displayError}</span>
        </p>
      )}
    </div>
  );
}

export const ACCEPTED_TYPES = ACCEPTED_PDF_MIME;