import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';

import { RootLayout } from '@/components/layout/RootLayout';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { Spinner } from '@/components/ui/Spinner';

const HomePage = lazy(() => import('@/pages/HomePage').then((m) => ({ default: m.HomePage })));
const LoginPage = lazy(() => import('@/pages/LoginPage').then((m) => ({ default: m.LoginPage })));
const RegisterPage = lazy(() =>
  import('@/pages/RegisterPage').then((m) => ({ default: m.RegisterPage })),
);
const TranslatePage = lazy(() =>
  import('@/pages/TranslatePage').then((m) => ({ default: m.TranslatePage })),
);
const DashboardPage = lazy(() =>
  import('@/pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
);
const GlossariesPage = lazy(() =>
  import('@/pages/GlossariesPage').then((m) => ({ default: m.GlossariesPage })),
);
const BillingPage = lazy(() =>
  import('@/pages/BillingPage').then((m) => ({ default: m.BillingPage })),
);
const ChangelogPage = lazy(() =>
  import('@/pages/ChangelogPage').then((m) => ({ default: m.ChangelogPage })),
);
const AboutPage = lazy(() =>
  import('@/pages/AboutPage').then((m) => ({ default: m.AboutPage })),
);
const NotFoundPage = lazy(() =>
  import('@/pages/NotFoundPage').then((m) => ({ default: m.NotFoundPage })),
);

const PageFallback = () => (
  <div className="flex min-h-[60vh] items-center justify-center">
    <Spinner size="lg" label="正在加载页面…" />
  </div>
);

const Protected = ({ children }: { children: React.ReactNode }) => (
  <RequireAuth>
    <Suspense fallback={<PageFallback />}>{children}</Suspense>
  </RequireAuth>
);

export function AppRouter() {
  return (
    <Routes>
      <Route element={<RootLayout />}>
        <Route
          path="/"
          element={
            <Suspense fallback={<PageFallback />}>
              <HomePage />
            </Suspense>
          }
        />
        <Route
          path="/login"
          element={
            <Suspense fallback={<PageFallback />}>
              <LoginPage />
            </Suspense>
          }
        />
        <Route
          path="/register"
          element={
            <Suspense fallback={<PageFallback />}>
              <RegisterPage />
            </Suspense>
          }
        />
        <Route
          path="/translate"
          element={
            <Protected>
              <TranslatePage />
            </Protected>
          }
        />
        <Route
          path="/dashboard"
          element={
            <Protected>
              <DashboardPage />
            </Protected>
          }
        />
        <Route
          path="/glossaries"
          element={
            <Protected>
              <GlossariesPage />
            </Protected>
          }
        />
        <Route
          path="/billing"
          element={
            <Protected>
              <BillingPage />
            </Protected>
          }
        />
        <Route
          path="/changelog"
          element={
            <Protected>
              <ChangelogPage />
            </Protected>
          }
        />
        <Route
          path="/about"
          element={
            <Suspense fallback={<PageFallback />}>
              <AboutPage />
            </Suspense>
          }
        />
        <Route path="/home" element={<Navigate to="/" replace />} />
        <Route
          path="*"
          element={
            <Suspense fallback={<PageFallback />}>
              <NotFoundPage />
            </Suspense>
          }
        />
      </Route>
    </Routes>
  );
}