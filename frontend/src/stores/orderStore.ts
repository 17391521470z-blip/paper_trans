import { create } from 'zustand';

import { apiGet, apiPost } from '@/lib/api';
import type { PlanCode } from '@/lib/constants';

export type PaymentMethod = 'wechat' | 'alipay';
export type OrderStatus = 'pending' | 'paid' | 'refunded' | 'cancelled' | 'expired';

export interface Order {
  id: string;
  order_no: string;
  tier: PlanCode | string;
  amount_cny: number;
  payment_method: PaymentMethod;
  status: OrderStatus;
  qr_code_url?: string | null;
  transaction_id?: string | null;
  paid_at?: string | null;
  expires_at?: string | null;
  created_at?: string;
  updated_at?: string;
}

interface OrderCreateResponse {
  id: string;
  order_no: string;
  tier: PlanCode | string;
  amount_cny: number;
  payment_method: PaymentMethod;
  qr_code_url: string | null;
  expires_at: string;
  status: OrderStatus;
  created_at: string;
}

interface OrderState {
  orders: Order[];
  currentOrder: OrderCreateResponse | null;
  isLoading: boolean;
  isCreating: boolean;
  errorMessage: string | null;
  fetchList: () => Promise<Order[]>;
  createOrder: (
    tier: PlanCode,
    paymentMethod: PaymentMethod,
    quantity?: number,
  ) => Promise<OrderCreateResponse>;
  clearCurrent: () => void;
}

export const useOrderStore = create<OrderState>((set, get) => ({
  orders: [],
  currentOrder: null,
  isLoading: false,
  isCreating: false,
  errorMessage: null,

  fetchList: async () => {
    set({ isLoading: true, errorMessage: null });
    try {
      const res = await apiGet<Order[]>('/orders');
      set({ orders: res, isLoading: false });
      return res;
    } catch (err) {
      const message = err instanceof Error ? err.message : '获取订单失败';
      set({ isLoading: false, errorMessage: message });
      return get().orders;
    }
  },

  createOrder: async (tier, paymentMethod, quantity = 1) => {
    set({ isCreating: true, errorMessage: null });
    try {
      const res = await apiPost<OrderCreateResponse>('/orders', {
        tier,
        payment_method: paymentMethod,
        quantity,
      });
      set({ currentOrder: res, isCreating: false });
      return res;
    } catch (err) {
      const message = err instanceof Error ? err.message : '创建订单失败';
      set({ isCreating: false, errorMessage: message });
      throw err;
    }
  },

  clearCurrent: () => set({ currentOrder: null }),
}));