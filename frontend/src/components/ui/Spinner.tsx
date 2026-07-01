import { cn } from '@/lib/utils';

export interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  label?: string;
  className?: string;
}

const sizeMap = {
  sm: 'h-4 w-4 border-2',
  md: 'h-6 w-6 border-2',
  lg: 'h-10 w-10 border-[3px]',
};

export function Spinner({ size = 'md', label, className }: SpinnerProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn('inline-flex items-center gap-3', className)}
    >
      <span
        className={cn(
          'inline-block animate-spin rounded-full border-brand-500 border-t-transparent',
          sizeMap[size],
        )}
        aria-hidden="true"
      />
      {label && <span className="text-sm text-ink-600">{label}</span>}
      <span className="sr-only">{label ?? '加载中'}</span>
    </div>
  );
}