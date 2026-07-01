import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  AtSign,
  Eye,
  EyeOff,
  Mail,
  Phone,
  ShieldCheck,
  UserPlus,
} from 'lucide-react';
import { toast } from 'sonner';

import { PageTitle } from '../components/seo/PageTitle';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/stores/authStore';

type Tab = 'email' | 'phone';

const COUNTDOWN_SECONDS = 60;

const TAB_ITEMS: {
  value: Tab;
  label: string;
  placeholder: string;
  icon: React.ComponentType<{ className?: string }>;
}[] = [
  { value: 'email', label: '邮箱', placeholder: 'you@example.com', icon: Mail },
  { value: 'phone', label: '手机号', placeholder: '+8613800000000', icon: Phone },
];

interface Strength {
  level: 0 | 1 | 2 | 3;
  label: string;
  color: string;
}

function evaluatePassword(value: string): Strength {
  if (!value) return { level: 0, label: '请输入密码', color: 'bg-ink-200' };
  let score = 0;
  if (value.length >= 8) score += 1;
  if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score += 1;
  if (/\d/.test(value)) score += 1;
  if (/[^\w\s]/.test(value)) score += 1;
  const level = Math.min(3, score) as 0 | 1 | 2 | 3;
  if (level === 0) return { level, label: '弱', color: 'bg-red-400' };
  if (level === 1) return { level, label: '较弱', color: 'bg-amber-400' };
  if (level === 2) return { level, label: '良好', color: 'bg-brand-400' };
  return { level, label: '强', color: 'bg-brand-600' };
}

export function RegisterPage() {
  const navigate = useNavigate();
  const register = useAuthStore((s) => s.register);
  const sendCode = useAuthStore((s) => s.sendCode);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  const [tab, setTab] = useState<Tab>('email');
  const [account, setAccount] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [nickname, setNickname] = useState('');
  const [agree, setAgree] = useState(false);

  const [showPassword, setShowPassword] = useState(false);
  const [sending, setSending] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const strength = useMemo(() => evaluatePassword(password), [password]);

  const validateAccount = useCallback((): string | null => {
    if (!account.trim()) {
      return tab === 'email' ? '请输入邮箱' : '请输入手机号';
    }
    if (tab === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(account)) {
      return '邮箱格式不正确';
    }
    if (tab === 'phone' && !/^\+?[1-9]\d{6,14}$/.test(account.replace(/\s/g, ''))) {
      return '手机号格式不正确';
    }
    return null;
  }, [account, tab]);

  const handleSendCode = useCallback(async () => {
    const accountError = validateAccount();
    if (accountError) {
      setErrors((prev) => ({ ...prev, account: accountError }));
      return;
    }
    setSending(true);
    setErrors((prev) => {
      const next = { ...prev };
      delete next.account;
      delete next.code;
      return next;
    });
    try {
      const res = await sendCode(account.trim(), tab, 'register');
      if (res.dev_code) {
        toast.info(`开发模式验证码：${res.dev_code}`, { duration: 6000 });
      } else {
        toast.success(`验证码已发送到 ${tab === 'email' ? '邮箱' : '手机'}`);
      }
      setCountdown(COUNTDOWN_SECONDS);
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            if (timerRef.current) clearInterval(timerRef.current);
            timerRef.current = null;
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    } catch (err) {
      const message = err instanceof Error ? err.message : '发送验证码失败';
      toast.error(message);
    } finally {
      setSending(false);
    }
  }, [account, sendCode, tab, validateAccount]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const next: Record<string, string> = {};

      const accountError = validateAccount();
      if (accountError) next.account = accountError;
      if (!code) next.code = '请输入验证码';
      else if (code.length < 4) next.code = '验证码至少 4 位';
      if (!password) next.password = '请输入密码';
      else if (password.length < 8) next.password = '密码至少 8 位';
      else if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
        next.password = '密码须同时包含字母与数字';
      }
      if (password !== confirmPassword) next.confirmPassword = '两次密码不一致';
      if (!agree) next.agree = '请阅读并同意服务条款';

      setErrors(next);
      if (Object.keys(next).length > 0) return;

      setSubmitting(true);
      try {
        await register({
          account: account.trim(),
          password,
          code,
          accountType: tab,
          nickname: nickname.trim() || undefined,
        });
        toast.success('注册成功，欢迎加入！');
        navigate('/', { replace: true });
      } catch (err) {
        const message = err instanceof Error ? err.message : '注册失败，请稍后重试';
        toast.error(message);
      } finally {
        setSubmitting(false);
      }
    },
    [
      account,
      agree,
      code,
      confirmPassword,
      navigate,
      nickname,
      password,
      register,
      tab,
      validateAccount,
    ],
  );

  const handleTabChange = useCallback((next: Tab) => {
    setTab(next);
    setAccount('');
    setCode('');
    setErrors({});
  }, []);

  return (
    <div className="container-page flex min-h-[calc(100vh-8rem)] items-center justify-center py-12">
      <PageTitle title="注册" />
      <Card className="w-full max-w-xl p-8">
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-brand-600 text-white">
            <UserPlus className="h-5 w-5" />
          </span>
          <h1 className="text-xl font-semibold text-ink-900">注册 PaperTranslate</h1>
          <p className="text-sm text-ink-500">30 秒创建账号，立即获得 30 页 / 月免费额度</p>
        </div>

        <div
          role="tablist"
          aria-label="注册方式"
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

          <div>
            <Input
              label="验证码"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="6 位验证码"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              error={errors.code}
              maxLength={6}
              disabled={submitting}
              required
              rightIcon={
                <button
                  type="button"
                  onClick={handleSendCode}
                  disabled={sending || countdown > 0 || submitting}
                  className={cn(
                    'whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium transition-colors',
                    countdown > 0 || sending || submitting
                      ? 'text-ink-400'
                      : 'text-brand-700 hover:bg-brand-50',
                  )}
                >
                  {sending
                    ? '发送中…'
                    : countdown > 0
                      ? `${countdown}s 后重试`
                      : '发送验证码'}
                </button>
              }
            />
          </div>

          <Input
            label="设置密码"
            type={showPassword ? 'text' : 'password'}
            autoComplete="new-password"
            placeholder="至少 8 位，含字母与数字"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={errors.password}
            hint={
              password
                ? `强度：${strength.label}`
                : '建议使用大小写字母、数字与符号组合'
            }
            disabled={submitting}
            required
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
          />

          {password && (
            <div className="flex gap-1" aria-hidden="true">
              {[0, 1, 2, 3].map((idx) => (
                <span
                  key={idx}
                  className={cn(
                    'h-1 flex-1 rounded-full transition-colors',
                    idx <= strength.level - 1 && strength.level > 0
                      ? strength.color
                      : 'bg-ink-200',
                  )}
                />
              ))}
            </div>
          )}

          <Input
            label="确认密码"
            type={showPassword ? 'text' : 'password'}
            autoComplete="new-password"
            placeholder="再次输入密码"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            error={errors.confirmPassword}
            disabled={submitting}
            required
          />

          <Input
            label="昵称（可选）"
            type="text"
            placeholder="你想展示的名字"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            disabled={submitting}
            maxLength={32}
          />

          <label className="flex items-start gap-2 text-sm text-ink-600">
            <input
              type="checkbox"
              checked={agree}
              onChange={(e) => setAgree(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-ink-300 text-brand-600 focus:ring-brand-500"
              disabled={submitting}
              aria-describedby={errors.agree ? 'agree-error' : undefined}
            />
            <span>
              我已阅读并同意{' '}
              <Link to="/" className="text-link">
                服务条款
              </Link>{' '}
              与{' '}
              <Link to="/" className="text-link">
                隐私政策
              </Link>
            </span>
          </label>
          {errors.agree && (
            <p id="agree-error" className="text-xs text-red-600">
              {errors.agree}
            </p>
          )}

          <Button
            type="submit"
            fullWidth
            isLoading={submitting}
            disabled={submitting}
            rightIcon={!submitting ? <ArrowRight className="h-4 w-4" /> : undefined}
          >
            {submitting ? '正在创建账号…' : '创建账号'}
          </Button>

          <p className="flex items-center justify-center gap-1 text-xs text-ink-500">
            <ShieldCheck className="h-3.5 w-3.5 text-brand-600" />
            我们不会向第三方分享你的联系方式
          </p>
        </form>

        <p className="mt-6 text-center text-sm text-ink-500">
          已有账号？
          <Link to="/login" className="text-link ml-1">
            直接登录
          </Link>
        </p>
      </Card>
    </div>
  );
}