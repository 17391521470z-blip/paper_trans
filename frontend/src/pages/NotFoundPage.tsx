import { Link } from 'react-router-dom';
import { ArrowLeft, Search } from 'lucide-react';

import { PageTitle } from '../components/seo/PageTitle';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';

export function NotFoundPage() {
  return (
    <div className="container-page flex min-h-[calc(100vh-8rem)] items-center justify-center py-12">
      <PageTitle title="页面未找到" />
      <Card className="flex w-full max-w-2xl flex-col items-center gap-6 p-10 text-center">
        <span className="inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-50 text-brand-700">
          <Search className="h-7 w-7" />
        </span>
        <div className="space-y-2">
          <p className="text-sm font-medium tracking-wider text-brand-600">404</p>
          <h1 className="text-2xl font-semibold text-ink-900">页面走丢了</h1>
          <p className="mx-auto max-w-md text-sm text-ink-500">
            看起来这个页面并不存在，或者已经被移动。你可以返回首页继续浏览，或前往翻译页上传一篇 PDF。
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Link to="/">
            <Button leftIcon={<ArrowLeft className="h-4 w-4" />}>返回首页</Button>
          </Link>
          <Link to="/translate">
            <Button variant="secondary">前往翻译</Button>
          </Link>
        </div>
      </Card>
    </div>
  );
}