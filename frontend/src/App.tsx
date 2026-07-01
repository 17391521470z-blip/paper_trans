import { Suspense } from 'react';

import { AppRouter } from '@/router';
import { Spinner } from '@/components/ui/Spinner';

export default function App() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-ink-50">
          <Spinner size="lg" label="正在加载页面" />
        </div>
      }
    >
      <AppRouter />
    </Suspense>
  );
}