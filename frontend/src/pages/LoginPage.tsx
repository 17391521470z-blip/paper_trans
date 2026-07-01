import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AtSign, Eye, EyeOff, LogIn, Mail, Phone } from 'lucide-react';
import { toast } from 'sonner';

import { PageTitle } from '../components/seo/PageTitle';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/stores/authStore';

type Tab = 'email' | 'phone';

const TAB_ITEMS: {
  value: Tab;
  label: string;
  placeholder: string;
  icon: React.ComponentType<{ className?: string }>;
}[] = [
  { value: 'email', label: '邮箱', placeholder: 'you@example.com', icon: Mail },
  { value: 'phone', label: '手机号', placeholder: '+8613800000000', icon: Phone },
];

export function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const from = params.get('from') ? decodeURIComponent(params.get('from')!) : '/translate';

  const login = useAuthStore((s) => s.login);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  const [tab, setTab] = useState<Tab>('email');
  const [account, setAccount] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<{ account?: string; password?: string }>({});

  useEffect(() => {
    if (isAuthenticated) {
      navigate(from, { replace: true });
    }
  }, [from, isAuthenticated, navigate]);

  const validate = useCallback((): boolean => {
    const next: { account?: string; password?: string } = {};
    if (!account.trim()) {
      next.account = tab === 'email' ? '请输入邮箱' : '请输入手机号';
    } else if (tab === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(account)) {
      next.account = '邮箱格式不正确';
    } else if (tab === 'phone' && !/^\+?[1-9]\d{6,14}$/.test(account.replace(/\s/g, ''))) {
      next.account = '手机号格式不正确';
    }
    if (!password) {
      next.password = '请输入密码';
    } else if (password.length < 6) {
      next.password = '密码至少 6 位';
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }, [account, password, tab]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!validate()) return;
      setSubmitting(true);
      try {
        await login({
          account: account.trim(),
          password,
          accountType: tab === 'phone' ? 'phone' : 'email',
        });
        toast.success('登录成功，正在跳转…');
        navigate(from, { replace: true });
      } catch (err) {
        const message =
          err instanceof Error ? err.message : '登录失败，请稍后重试。';
        toast.error(message);
      } finally {
        setSubmitting(false);
      }
    },
    [account, from, login, navigate, password, tab, validate],
  );

  const handleTabChange = useCallback((next: Tab) => {
    setTab(next);
    setAccount('');
    setErrors((prev) => ({ ...prev, account: undefined }));
  }, []);

  return (
    <div className="container-page flex min-h-[calc(100vh-8rem)] items-center justify-center py-12">
      <PageTitle title="登录" />
      <div className="grid w-full max-w-5xl gap-8 lg:grid-cols-2">
        <div className="hidden flex-col justify-between rounded-2xl bg-gradient-to-br from-brand-700 to-brand-900 p-10 text-white lg:flex">
          <div className="space-y-4">
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-white/15 text-sm font-bold">
              PT
            </span>
            <h2 className="text-2xl font-semibold leading-snug">
              把翻译的时间，
              <br />
              留给真正的科研
            </h2>
            <p className="text-sm text-brand-50/80">
              登录后即可上传 PDF、配置术语库、跟踪翻译历史。
              翻译结果会保留公式、图表与参考文献格式。
            </p>
          </div>
          <ul className="space-y-2 text-sm text-brand-50/80">
            <li>· 30 页 / 月免费额度，即开即用</li>
            <li>· 双 / 单语 PDF 多格式导出</li>
            <li>· 术语库跨任务复用，避免翻译漂移</li>
          </ul>
        </div>

        <Card className="p-8">
          <div className="mb-6 flex flex-col items-center gap-2 text-center">
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-brand-600 text-white">
              <LogIn className="h-5 w-5" />
            </span>
            <h1 className="text-xl font-semibold text-ink-900">登录 PaperTranslate</h1>
            <p className="text-sm text-ink-500">
              使用注册时的手机号或邮箱继续
            </p>
          </div>

          <div
            role="tablist"
            aria-label="登录方式"
            className="mb-6 grid grid-cols-2 gap-1 rounded-lg bg-ink-100 p-1"
          >
            {TAB_ITEMS.map((item) => (
              <button
                key={item.value}
                type="button"
                role="tab"
                aria-selected={tab === item.value}
                onClick={() => handleTabChange(item.value)}
                className={cn(
                  'inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  tab === item.value
                    ? 'bg-white text-ink-900 shadow-sm'
                    : 'text-ink-500 hover:text-ink-700',
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </button>
            ))}
          </div>

          <form className="space-y-4" onSubmit={handleSubmit} noValidate>
            <Input
              label={tab === 'email' ? '邮箱' : '手机号'}
              type={tab === 'email' ? 'email' : 'tel'}
              autoComplete={tab === 'email' ? 'email' : 'tel'}
              placeholder={tab === 'email' ? 'you@example.com' : '+8613800000000'}
              value={account}
              onChange={(e) => setAccount(e.target.value)}
              error={errors.account}
              leftIcon={
                tab === 'email' ? <AtSign className="h-4 w-4" /> : <Phone className="h-4 w-4" />
              }
              disabled={submitting}
              required
            />

            <Input
              label="密码"
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              placeholder="请输入密码"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={errors.password}
              rightIcon={
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="text-ink-400 hover:text-ink-600"
                  aria-label={showPassword ? '隐藏密码' : '显示密码'}
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              }
              disabled={submitting}
              required
            />

            <label className="flex items-center gap-2 text-sm text-ink-600">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="h-4 w-4 rounded border-ink-300 text-brand-600 focus:ring-brand-500"
                disabled={submitting}
              />
              <span>保持登录 30 天</span>
            </label>

            <Button
              type="submit"
              fullWidth
              isLoading={submitting}
              disabled={submitting}
              leftIcon={!submitting ? <LogIn className="h-4 w-4" /> : undefined}
            >
              {submitting ? '正在登录…' : '登录'}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-ink-500">
            还没有账号？
            <Link to="/register" className="text-link ml-1">
              立即注册
            </Link>
          </p>
        </Card>
      </div>
    </div>
  );
}