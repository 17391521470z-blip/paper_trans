import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RefreshCcw } from 'lucide-react';
import { Button } from './Button';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    if (import.meta.env.DEV) {
      console.error('[ErrorBoundary]', error, info);
    }
  }

  private handleReload = () => {
    if (typeof window !== 'undefined') {
      window.location.reload();
    }
  };

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    if (this.props.fallback) {
      return this.props.fallback;
    }

    return (
      <div className="flex min-h-screen items-center justify-center bg-ink-50 px-4">
        <div className="surface-card w-full max-w-md p-8 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-red-600">
            <AlertTriangle className="h-6 w-6" aria-hidden="true" />
          </div>
          <h1 className="text-lg font-semibold text-ink-900">
            页面出现了意外错误
          </h1>
          <p className="mt-2 text-sm text-ink-500">
            我们已记录这次问题。你可以刷新页面重试，或返回首页继续操作。
          </p>
          {this.state.error && import.meta.env.DEV && (
            <pre className="mt-4 max-h-32 overflow-auto rounded-md bg-ink-100 p-3 text-left text-xs text-ink-700">
              {this.state.error.message}
            </pre>
          )}
          <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-center">
            <Button onClick={this.handleReload} leftIcon={<RefreshCcw className="h-4 w-4" />}>
              刷新页面
            </Button>
            <Button variant="secondary" onClick={this.handleReset}>
              重试
            </Button>
          </div>
        </div>
      </div>
    );
  }
}