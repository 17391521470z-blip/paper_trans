import { create } from 'zustand';

import { apiDelete, apiGet, apiUpload, type ApiError } from '@/lib/api';

export type TaskStatus =
  | 'idle'
  | 'uploading'
  | 'pending'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface TaskInfo {
  id: string;
  filename: string;
  file_size?: number;
  page_count?: number;
  status: TaskStatus;
  progress: number;
  source_language?: string;
  target_language?: string;
  llm_service?: string;
  glossary_id?: string | null;
  result_url?: string | null;
  result_mono_url?: string | null;
  result_md_url?: string | null;
  result_docx_url?: string | null;
  error_message?: string | null;
  created_at?: string;
  updated_at?: string;
  completed_at?: string | null;
  cost_cny?: number;
}

export interface TaskSubmission {
  file: File;
  sourceLang: string;
  targetLang: string;
  service: string;
  model?: string;
  glossaryId?: string | null;
}

interface TaskCreateResponse {
  task_id: string;
  cached?: boolean;
}

interface TaskListResponse {
  items: TaskInfo[];
  total: number;
  page: number;
  page_size: number;
}

interface TaskState {
  currentTask: TaskInfo | null;
  progress: number;
  status: TaskStatus;
  errorMessage: string | null;
  isSubmitting: boolean;
  uploadProgress: number;
  recentTasks: TaskInfo[];
  listPage: number;
  listPageSize: number;
  listTotal: number;
  listLoading: boolean;
  submitTask: (
    payload: TaskSubmission,
    onUploadProgress?: (percent: number) => void,
  ) => Promise<TaskInfo>;
  fetchTask: (taskId: string) => Promise<TaskInfo | null>;
  fetchRecentTasks: (page?: number, pageSize?: number) => Promise<TaskInfo[]>;
  deleteTask: (taskId: string) => Promise<void>;
  updateProgress: (progress: number, status?: TaskStatus) => void;
  setTask: (task: TaskInfo | null) => void;
  setError: (message: string | null) => void;
  reset: () => void;
}

export const useTaskStore = create<TaskState>((set) => ({
  currentTask: null,
  progress: 0,
  status: 'idle',
  errorMessage: null,
  isSubmitting: false,
  uploadProgress: 0,
  recentTasks: [],
  listPage: 1,
  listPageSize: 10,
  listTotal: 0,
  listLoading: false,

  submitTask: async (payload, onUploadProgress) => {
    set({
      isSubmitting: true,
      errorMessage: null,
      status: 'uploading',
      uploadProgress: 0,
      progress: 0,
    });

    try {
      const formData = new FormData();
      formData.append('file', payload.file);
      formData.append('source_language', payload.sourceLang);
      formData.append('target_language', payload.targetLang);
      formData.append('llm_service', payload.service);
      if (payload.glossaryId) {
        formData.append('glossary_id', payload.glossaryId);
      }

      const res = await apiUpload<TaskCreateResponse>('/tasks', formData, (percent) => {
        set({ uploadProgress: percent });
        onUploadProgress?.(percent);
      });

      const placeholder: TaskInfo = {
        id: res.task_id,
        filename: payload.file.name,
        file_size: payload.file.size,
        status: 'pending',
        progress: 0,
        source_language: payload.sourceLang,
        target_language: payload.targetLang,
        llm_service: payload.service,
        glossary_id: payload.glossaryId ?? null,
        result_url: null,
        result_mono_url: null,
        result_md_url: null,
        result_docx_url: null,
      };

      set({
        currentTask: placeholder,
        status: 'pending',
        progress: 0,
        uploadProgress: 100,
        isSubmitting: false,
      });

      try {
        const fresh = await apiGet<TaskInfo>(`/tasks/${res.task_id}`);
        set({ currentTask: fresh, progress: fresh.progress ?? 0, status: fresh.status });
        return fresh;
      } catch {
        return placeholder;
      }
    } catch (err) {
      set({
        isSubmitting: false,
        status: 'failed',
        uploadProgress: 0,
        errorMessage: (err as ApiError)?.message ?? '上传失败，请重试',
      });
      throw err;
    }
  },

  fetchTask: async (taskId) => {
    try {
      const fresh = await apiGet<TaskInfo>(`/tasks/${taskId}`);
      set({ currentTask: fresh, progress: fresh.progress, status: fresh.status });
      return fresh;
    } catch {
      return null;
    }
  },

  fetchRecentTasks: async (page = 1, pageSize = 10) => {
    set({ listLoading: true });
    try {
      const res = await apiGet<TaskListResponse>(
        `/tasks?page=${page}&page_size=${pageSize}`,
      );
      set({
        recentTasks: res.items,
        listPage: res.page,
        listPageSize: res.page_size,
        listTotal: res.total,
        listLoading: false,
      });
      return res.items;
    } catch {
      set({ listLoading: false });
      return [];
    }
  },

  deleteTask: async (taskId) => {
    await apiDelete<void>(`/tasks/${taskId}`);
    set((state) => ({
      recentTasks: state.recentTasks.filter((t) => t.id !== taskId),
      currentTask:
        state.currentTask?.id === taskId ? null : state.currentTask,
    }));
  },

  updateProgress: (progress, status) =>
    set((state) => ({
      progress: Math.max(0, Math.min(100, progress)),
      status: status ?? state.status,
    })),

  setTask: (task) =>
    set({
      currentTask: task,
      progress: task?.progress ?? (task?.status === 'completed' ? 100 : 0),
      status: task?.status ?? 'idle',
      errorMessage: task?.error_message ?? null,
    }),

  setError: (message) =>
    set({ errorMessage: message, status: 'failed', isSubmitting: false }),

  reset: () =>
    set({
      currentTask: null,
      progress: 0,
      status: 'idle',
      errorMessage: null,
      isSubmitting: false,
      uploadProgress: 0,
    }),
}));