import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

import {
  apiGet,
  apiPost,
  setAuthToken,
  registerUnauthorizedHandler,
} from '@/lib/api';

export type AccountType = 'phone' | 'email' | 'auto';

export interface AuthUser {
  id: string;
  phone?: string | null;
  email?: string | null;
  nickname?: string | null;
  display_name?: string | null;
  avatar_url?: string | null;
  is_verified?: boolean;
  tier?: string;
  plan?: string;
  created_at?: string;
}

interface TokenResponse {
  access_token: string;
  token_type?: string;
  expires_in?: number;
  user_id?: string;
}

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isHydrated: boolean;
  setSession: (token: string, user: AuthUser) => void;
  setUser: (user: AuthUser | null) => void;
  clearSession: () => void;
  sendCode: (
    account: string,
    accountType: 'phone' | 'email',
    purpose?: 'register' | 'login' | 'reset',
  ) => Promise<{ success: boolean; dev_code?: string }>;
  register: (payload: {
    account: string;
    password: string;
    code: string;
    accountType: 'phone' | 'email';
    nickname?: string;
  }) => Promise<AuthUser>;
  login: (payload: {
    account: string;
    password: string;
    accountType?: AccountType;
  }) => Promise<AuthUser>;
  fetchProfile: () => Promise<AuthUser | null>;
  logout: () => void;
}

async function loadProfile(): Promise<AuthUser | null> {
  try {
    const profile = await apiGet<AuthUser>('/users/me');
    return {
      ...profile,
      display_name: profile.nickname ?? profile.email ?? profile.phone ?? null,
      plan: (profile as { tier?: string }).tier,
    };
  } catch {
    return null;
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      isHydrated: false,

      setSession: (token, user) => {
        setAuthToken(token);
        set({ token, user, isAuthenticated: true });
      },

      setUser: (user) =>
        set({
          user,
          isAuthenticated: Boolean(user && get().token),
        }),

      clearSession: () => {
        setAuthToken(null);
        set({ token: null, user: null, isAuthenticated: false });
      },

      sendCode: async (account, accountType, purpose = 'register') => {
        return apiPost<{ success: boolean; dev_code?: string }>(
          '/auth/send-code',
          { account, account_type: accountType, purpose },
        );
      },

      register: async ({ account, password, code, accountType, nickname }) => {
        const res = await apiPost<TokenResponse>('/auth/register', {
          account,
          password,
          code,
          account_type: accountType,
          nickname,
        });
        setAuthToken(res.access_token);
        set({ token: res.access_token });
        const profile = await loadProfile();
        const user: AuthUser = profile ?? {
          id: res.user_id ?? '',
          email: accountType === 'email' ? account : null,
          phone: accountType === 'phone' ? account : null,
          nickname: nickname ?? null,
          display_name: nickname ?? account,
        };
        set({ user, isAuthenticated: true });
        return user;
      },

      login: async ({ account, password, accountType = 'auto' }) => {
        const res = await apiPost<TokenResponse>('/auth/login', {
          account,
          password,
          account_type: accountType,
        });
        setAuthToken(res.access_token);
        set({ token: res.access_token });
        const profile = await loadProfile();
        let user: AuthUser;
        if (profile) {
          user = profile;
        } else {
          const isPhone = accountType === 'phone';
          user = {
            id: res.user_id ?? '',
            email: !isPhone && account.includes('@') ? account : null,
            phone: isPhone ? account : null,
            display_name: account,
          };
        }
        set({ user, isAuthenticated: true });
        return user;
      },

      fetchProfile: async () => {
        const profile = await loadProfile();
        if (profile) {
          set({
            user: { ...profile, display_name: profile.nickname ?? profile.email ?? profile.phone ?? null },
          });
        }
        return profile;
      },

      logout: () => {
        setAuthToken(null);
        set({ token: null, user: null, isAuthenticated: false });
      },
    }),
    {
      name: 'pt.auth',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
      onRehydrateStorage: () => (state, error) => {
        if (error && import.meta.env.DEV) {
          console.warn('[authStore] rehydrate error', error);
        }
        if (state?.token) {
          setAuthToken(state.token);
        }
        if (state) {
          state.isHydrated = true;
        }
      },
    },
  ),
);

if (typeof window !== 'undefined') {
  registerUnauthorizedHandler(() => {
    useAuthStore.getState().clearSession();
  });
}