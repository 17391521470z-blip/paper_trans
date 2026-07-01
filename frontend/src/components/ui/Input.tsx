import { forwardRef, type InputHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  fullWidth?: boolean;
}

let inputCounter = 0;
const genId = () => `pt-input-${++inputCounter}`;

export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      hint,
      error,
      leftIcon,
      rightIcon,
      fullWidth = true,
      className,
      id,
      ...rest
    },
    ref,
  ) => {
    const reactId = (rest as { id?: string }).id;
    const inputId = id ?? reactId ?? genId();
    const describedById = hint || error ? `${inputId}-desc` : undefined;

    return (
      <div className={cn('flex flex-col gap-1.5', fullWidth && 'w-full')}>
        {label && (
          <label
            htmlFor={inputId}
            className="text-sm font-medium text-ink-700"
          >
            {label}
          </label>
        )}
        <div className="relative">
          {leftIcon && (
            <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-ink-400">
              {leftIcon}
            </span>
          )}
          <input
            ref={ref}
            id={inputId}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedById}
            className={cn(
              'h-10 w-full rounded-lg border bg-white px-3 text-sm text-ink-900 placeholder:text-ink-400',
              'focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30',
              'disabled:cursor-not-allowed disabled:bg-ink-50 disabled:text-ink-400',
              error
                ? 'border-red-400 focus:border-red-500 focus:ring-red-500/30'
                : 'border-ink-200',
              leftIcon && 'pl-9',
              rightIcon && 'pr-9',
              className,
            )}
            {...rest}
          />
          {rightIcon && (
            <span className="absolute inset-y-0 right-3 flex items-center text-ink-400">
              {rightIcon}
            </span>
          )}
        </div>
        {(hint || error) && (
          <p
            id={describedById}
            className={cn(
              'text-xs',
              error ? 'text-red-600' : 'text-ink-500',
            )}
          >
            {error || hint}
          </p>
        )}
      </div>
    );
  },
);

Input.displayName = 'Input';