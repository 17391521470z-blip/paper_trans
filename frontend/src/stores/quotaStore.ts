import { create } from 'zustand';

import { apiGet } from '@/lib/api';
import type { PlanCode } from '@/lib/constants';

export interface QuotaInfo {
  tier: PlanCode | string;
  monthly_pages: number;
  used_pages: number;
  remaining_pages: number;
  daily_pages: number;
  used_daily_pages: number;
  remaining_daily_pages: number;
  reset_at?: string | null;
  daily_reset_at?: string | null;
}

interface QuotaState {
  quota: QuotaInfo | null;
  isLoading: boolean;
  errorMessage: string | null;
  refresh: () => Promise<QuotaInfo | null>;
  setQuota: (quota: QuotaInfo | null) => void;
}

export const useQuotaStore = create<QuotaState>((set, get) => ({
  quota: null,
  isLoading: false,
  errorMessage: null,

  refresh: async () => {
    set({ isLoading: true, errorMessage: null });
    try {
      const res = await apiGet<QuotaInfo>('/quotas');
      set({ quota: res, isLoading: false });
      return res;
    } catch (err) {
      const message = err instanceof Error ? err.message : '获取配额信息失败';
      set({ isLoading: false, errorMessage: message });
      return get().quota;
    }
  },

  setQuota: (quota) => set({ quota }),
}));