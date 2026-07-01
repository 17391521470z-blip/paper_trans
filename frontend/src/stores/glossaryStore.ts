import { create } from 'zustand';

import { apiDelete, apiGet, apiPost } from '@/lib/api';

export interface GlossaryTerm {
  term: string;
  translation: string;
  context?: string;
}

export interface Glossary {
  id: string;
  name: string;
  description?: string | null;
  domain?: string;
  term_count: number;
  is_active: boolean;
  is_builtin?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface GlossaryDetail extends Glossary {
  terms: GlossaryTerm[];
}

interface GlossaryCreateResponse {
  glossary_id: string;
  term_count: number;
  skipped: number;
  warnings: string[];
}

interface GlossaryState {
  list: Glossary[];
  isLoading: boolean;
  errorMessage: string | null;
  fetchList: () => Promise<Glossary[]>;
  upload: (file: File, name: string, description?: string) => Promise<Glossary>;
  remove: (id: string) => Promise<void>;
  getDetail: (id: string) => Promise<GlossaryDetail | null>;
}

export const useGlossaryStore = create<GlossaryState>((set, get) => ({
  list: [],
  isLoading: false,
  errorMessage: null,

  fetchList: async () => {
    set({ isLoading: true, errorMessage: null });
    try {
      const res = await apiGet<Glossary[]>('/glossaries');
      set({ list: res, isLoading: false });
      return res;
    } catch (err) {
      const message = err instanceof Error ? err.message : '获取术语库失败';
      set({ isLoading: false, errorMessage: message });
      return get().list;
    }
  },

  upload: async (file, name, description) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', name);
    if (description) formData.append('description', description);

    const res = await apiPost<GlossaryCreateResponse>(
      '/glossaries',
      formData,
    );

    const refreshed = await get().fetchList();
    const created = refreshed.find((g) => g.id === res.glossary_id);
    return (
      created ?? {
        id: res.glossary_id,
        name,
        description: description ?? null,
        term_count: res.term_count,
        is_active: true,
      }
    );
  },

  remove: async (id) => {
    await apiDelete<void>(`/glossaries/${id}`);
    set((state) => ({ list: state.list.filter((g) => g.id !== id) }));
  },

  getDetail: async (id) => {
    try {
      return await apiGet<GlossaryDetail>(`/glossaries/${id}`);
    } catch {
      return null;
    }
  },
}));