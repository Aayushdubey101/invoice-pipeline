import type {
  InvoiceDetail,
  ReviewQueue,
  UploadResponse,
  Vendor,
  VendorList,
} from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Phase 14 — active workspace id, kept in sync by WorkspaceSessionContext ──
// A plain module-level value (not React state) since `request()` and the raw
// XHR in `batch.upload()` are called from outside any component tree.
let currentWorkspaceId: string | null = null;

export function setWorkspaceId(id: string | null): void {
  currentWorkspaceId = id;
}

let currentClerkToken: string | null = null;

export function setClerkToken(token: string | null): void {
  currentClerkToken = token;
}

// ── Auth-ready gate ──────────────────────────────────────────────────────────
// The first Clerk token sync is async (ClerkTokenSyncProvider). Without this,
// a page's data-fetch effect can call request() before that sync resolves,
// sending neither Authorization nor X-Workspace-Id. Resolved once per app
// load, then a no-op forever after.
let resolveAuthReady: () => void;
export const authReadyPromise = new Promise<void>((resolve) => {
  resolveAuthReady = resolve;
});
export function markAuthReady(): void {
  resolveAuthReady();
}

export type CloudProviderName = "openai" | "anthropic" | "gemini" | "groq";

export interface ProviderHeaders {
  provider: CloudProviderName;
  apiKey: string;
  model: string;
  config?: Record<string, unknown>;
}

export interface AppSettings {
  llm_provider: string;
  lm_studio_model: string;
  lm_studio_base_url: string;
  llamacpp_base_url: string;
  llamacpp_model: string;
  has_llamacpp_key: boolean;
  llamacpp_context_length: number;
  llamacpp_temperature: number;
  llamacpp_max_tokens: number;
  ollama_base_url: string;
  ollama_model: string;
}

export interface SettingsUpdatePayload {
  llm_provider: string;
  lm_studio_model: string;
  lm_studio_base_url: string;
  llamacpp_base_url: string;
  llamacpp_model: string;
  llamacpp_api_key: string;
  llamacpp_context_length: number;
  llamacpp_temperature: number;
  llamacpp_max_tokens: number;
  ollama_base_url: string;
  ollama_model: string;
}

export interface ProviderPreference {
  provider: CloudProviderName;
  model: string;
  config: Record<string, unknown>;
  has_saved_api_key?: boolean;
}

export interface WorkspaceInfo {
  id: string;
  workspace_type: string;
  status: string;
  expires_at: string | null;
  created_at: string;
}

export interface TestConnectionResult {
  online: boolean;
  models?: string[];
  error?: string;
  message?: string;
  latency_ms?: number;
  endpoint?: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  await authReadyPromise;
  const isFormData = init?.body instanceof FormData;
  const { headers: initHeaders, ...restInit } = init ?? {};
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...(initHeaders as Record<string, string> | undefined),
  };
  if (currentClerkToken) {
    headers["Authorization"] = `Bearer ${currentClerkToken}`;
  } else if (currentWorkspaceId) {
    headers["X-Workspace-Id"] = currentWorkspaceId;
  }

  const res = await fetch(`${API_BASE}${path}`, { ...restInit, headers });

  if (!res.ok) {
    const problem = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(problem.detail ?? `HTTP ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const apiClient = {
  health: () => request<{ status: string; version: string }>("/health"),

  // ── Phase 14 — guest workspace lifecycle ───────────────────────────────────
  workspaces: {
    create: () => request<WorkspaceInfo>("/workspaces", { method: "POST" }),
    get: (id: string) => request<WorkspaceInfo>(`/workspaces/${id}`),
    me: () => request<WorkspaceInfo>("/workspaces/me"),
    delete: (id: string) => request<void>(`/workspaces/${id}`, { method: "DELETE" }),
    migrate: (guestWorkspaceId: string) =>
      request<{ status: string; migrated_from: string; migrated_to: string }>("/workspaces/migrate", {
        method: "POST",
        body: JSON.stringify({ guest_workspace_id: guestWorkspaceId }),
      }),
    getProviderPreference: (workspaceId: string) =>
      request<Partial<ProviderPreference>>(`/workspaces/${workspaceId}/provider-preference`),
    updateProviderPreference: (workspaceId: string, preference: Omit<ProviderPreference, "has_saved_api_key">, apiKey?: string) =>
      request<ProviderPreference>(`/workspaces/${workspaceId}/provider-preference`, {
        method: "PATCH",
        body: JSON.stringify({ preference, api_key: apiKey }),
      }),
  },

  // ── Phase 14.6 — Finish Session (PDF+Excel+JSON zip, then purge) ───────────
  session: {
    finish: async (): Promise<Blob> => {
      await authReadyPromise;
      const headers: Record<string, string> = {};
      if (currentClerkToken) {
        headers["Authorization"] = `Bearer ${currentClerkToken}`;
      } else if (currentWorkspaceId) {
        headers["X-Workspace-Id"] = currentWorkspaceId;
      }
      const res = await fetch(`${API_BASE}/session/finish`, { method: "POST", headers });
      if (!res.ok) {
        const problem = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(problem.detail ?? `HTTP ${res.status}`);
      }
      
      // Clear all guest configuration state
      if (typeof window !== "undefined") {
        window.sessionStorage.removeItem("invoice_pipeline_provider_session");
        window.sessionStorage.removeItem("invoice_pipeline_workspace_session");
      }
      
      return res.blob();
    },
  },

  documents: {
    upload: (file: File): Promise<UploadResponse> => {
      const form = new FormData();
      form.append("file", file);
      return request<UploadResponse>("/documents/upload", {
        method: "POST",
        body: form,
      });
    },
    get: (id: string) => request<InvoiceDetail>(`/documents/${id}`),
    // /file is rendered via <img>/<Document>, which can't send custom headers —
    // fetch it ourselves (with the same auth headers as everything else) and
    // hand the viewer a blob: URL instead of the raw, auth-walled API URL.
    fileBlobUrl: async (id: string): Promise<string> => {
      await authReadyPromise;
      const headers: Record<string, string> = {};
      if (currentClerkToken) {
        headers["Authorization"] = `Bearer ${currentClerkToken}`;
      } else if (currentWorkspaceId) {
        headers["X-Workspace-Id"] = currentWorkspaceId;
      }
      const res = await fetch(`${API_BASE}/documents/${id}/file`, { headers });
      if (!res.ok) {
        const problem = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(problem.detail ?? `HTTP ${res.status}`);
      }
      return URL.createObjectURL(await res.blob());
    },
  },

  invoices: {
    get: (id: string) => request<InvoiceDetail>(`/invoices/${id}`),
  },

  review: {
    queue: () => request<ReviewQueue>("/review/queue"),
    approve: (invoiceId: string) =>
      request<{ invoice_id: string; status: string }>(`/review/${invoiceId}/approve`, {
        method: "POST",
      }),
    reject: (invoiceId: string) =>
      request<{ invoice_id: string; status: string }>(`/review/${invoiceId}/reject`, {
        method: "POST",
      }),
    updateField: (invoiceId: string, fieldId: string, reviewedValue: string | null) =>
      request<{ field_id: string; reviewed_value: string | null }>(
        `/review/${invoiceId}/field/${fieldId}`,
        {
          method: "PATCH",
          body: JSON.stringify({ reviewed_value: reviewedValue }),
        }
      ),
  },

  vendors: {
    list: () => request<VendorList>("/vendors/"),
    update: (vendorId: string, data: Partial<Pick<Vendor, "canonical_name" | "aliases" | "status">>) =>
      request<Vendor>(`/vendors/${vendorId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
  },

  settings: {
    get: () => request<AppSettings>("/settings/"),
    update: (data: Partial<SettingsUpdatePayload>) =>
      request<AppSettings>("/settings/", {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    getLmStudioModels: (baseUrl?: string) => request<{
      online: boolean;
      models: string[];
      error?: string;
    }>(`/settings/lm-studio-models${baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : ""}`),
    llamacppHealth: (baseUrl?: string) => request<{
      online: boolean;
      status_code?: number;
      latency_ms?: number;
      endpoint?: string;
      error?: string;
      message?: string;
      body?: unknown;
    }>(`/settings/llamacpp/health${baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : ""}`),
    llamacppModels: (baseUrl?: string) => request<{
      online: boolean;
      models: string[];
      error?: string;
      message?: string;
    }>(`/settings/llamacpp/models${baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : ""}`),
    getOllamaModels: (baseUrl?: string) => request<{
      online: boolean;
      models: string[];
      error?: string;
    }>(`/settings/ollama-models${baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : ""}`),
    testConnection: (provider: string, opts?: { apiKey?: string; baseUrl?: string }) => {
      const qs = new URLSearchParams({ provider });
      if (opts?.apiKey) qs.set("api_key", opts.apiKey);
      if (opts?.baseUrl) qs.set("base_url", opts.baseUrl);
      return request<TestConnectionResult>(`/settings/test-connection?${qs.toString()}`, {
        method: "POST",
      });
    },
  },

  llm: {
    status: () => request<{
      provider: string;
      model: string;
      endpoint: string | null;
    }>("/llm/status"),
  },

  // ── Phase 13 — browser-session BYOK cloud providers ──────────────────────────

  providers: {
    test: (input: {
      provider: CloudProviderName;
      apiKey: string;
      model: string;
      config?: Record<string, unknown>;
    }) =>
      request<{ success: boolean; latency_ms: number; error: string | null }>("/providers/test", {
        method: "POST",
        body: JSON.stringify({
          provider: input.provider,
          api_key: input.apiKey,
          model: input.model,
          config: input.config ?? {},
        }),
      }),
  },

  // ── Phase 11 ────────────────────────────────────────────────────────────────

  batch: {
    /** Upload multiple files as a single batch, with real upload progress + cancellation.
     * Resolves as soon as the batch is accepted — processing continues server-side;
     * poll `batch.get(batch_id)` for progress. */
    upload: (
      files: File[],
      uploadSource = "web",
      opts?: {
        onProgress?: (percent: number) => void;
        signal?: AbortSignal;
        providerHeaders?: ProviderHeaders;
      }
    ): Promise<BatchUploadAcceptedResponse> => {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      return authReadyPromise.then(() => new Promise<BatchUploadAcceptedResponse>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${API_BASE}/batch/upload?upload_source=${encodeURIComponent(uploadSource)}`);
        const ph = opts?.providerHeaders;
        if (ph) {
          xhr.setRequestHeader("X-LLM-Provider", ph.provider);
          xhr.setRequestHeader("X-LLM-Api-Key", ph.apiKey);
          xhr.setRequestHeader("X-LLM-Model", ph.model);
          xhr.setRequestHeader("X-LLM-Config", JSON.stringify(ph.config ?? {}));
        }
        if (currentClerkToken) {
          xhr.setRequestHeader("Authorization", `Bearer ${currentClerkToken}`);
        } else if (currentWorkspaceId) {
          xhr.setRequestHeader("X-Workspace-Id", currentWorkspaceId);
        }
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) opts?.onProgress?.(Math.round((e.loaded / e.total) * 100));
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              resolve(JSON.parse(xhr.responseText) as BatchUploadAcceptedResponse);
            } catch {
              reject(new Error("Invalid server response"));
            }
          } else {
            let detail = xhr.statusText;
            try {
              detail = JSON.parse(xhr.responseText).detail ?? detail;
            } catch {
              // non-JSON error body — fall back to statusText
            }
            reject(new Error(detail || `HTTP ${xhr.status}`));
          }
        };
        xhr.onerror = () => reject(new Error("Network error during upload"));
        xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));
        if (opts?.signal) {
          if (opts.signal.aborted) {
            xhr.abort();
            return;
          }
          opts.signal.addEventListener("abort", () => xhr.abort());
        }
        xhr.send(form);
      }));
    },
    list: (skip = 0, limit = 50) =>
      request<{ batches: BatchSummary[]; total: number }>(
        `/batch/?skip=${skip}&limit=${limit}`
      ),
    get: (batchId: string) => request<BatchDetail>(`/batch/${batchId}`),
    retryFailed: (batchId: string) =>
      request<{ batch_id: string; retried: number }>(`/batch/${batchId}/retry-failed`, {
        method: "POST",
      }),
  },

  export: {
    /** Download invoices as an Excel file */
    excel: (params: ExportParams = {}): string => {
      const qs = new URLSearchParams();
      if (params.batchId) qs.set("batch_id", params.batchId);
      if (params.vendorId) qs.set("vendor_id", params.vendorId);
      if (params.startDate) qs.set("start_date", params.startDate);
      if (params.endDate) qs.set("end_date", params.endDate);
      if (params.reviewStatus) qs.set("review_status", params.reviewStatus);
      if (params.invoiceIds?.length) {
        params.invoiceIds.forEach((id) => qs.append("invoice_ids", id));
      }
      return `${API_BASE}/export/excel?${qs.toString()}`;
    },
    history: () => request<{ exports: ExportHistoryItem[] }>("/export/history"),
  },

  dashboard: {
    stats: () => request<DashboardStats>("/dashboard/stats"),
    search: (params: SearchParams) => {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.vendor) qs.set("vendor", params.vendor);
      if (params.invoiceNumber) qs.set("invoice_number", params.invoiceNumber);
      if (params.startDate) qs.set("start_date", params.startDate);
      if (params.endDate) qs.set("end_date", params.endDate);
      if (params.batchId) qs.set("batch_id", params.batchId);
      if (params.status) qs.set("status", params.status);
      if (params.minConfidence != null) qs.set("min_confidence", String(params.minConfidence));
      if (params.skip != null) qs.set("skip", String(params.skip));
      if (params.limit != null) qs.set("limit", String(params.limit));
      return request<{ total: number; items: SearchInvoiceItem[] }>(
        `/dashboard/search?${qs.toString()}`
      );
    },
  },
};

// ── Phase 11 types ─────────────────────────────────────────────────────────────

export interface BatchUploadAcceptedResponse {
  batch_id: string;
  upload_source: string;
  total_files: number;
  status: string;
}

export interface BatchSummary {
  batch_id: string;
  upload_source: string;
  total_files: number;
  completed: number;
  failed: number;
  pending: number;
  skipped: number;
  avg_confidence: number | null;
  processing_time_ms: number | null;
  created_at: string;
}

export interface BatchDetail extends BatchSummary {
  documents: {
    document_id: string;
    filename: string;
    status: string;
    errors?: { stage: string; message: string; detail: string | null; fatal: boolean }[];
    invoice_id: string | null;
    created_at: string;
  }[];
}

export interface ExportParams {
  invoiceIds?: string[];
  batchId?: string;
  vendorId?: string;
  startDate?: string;
  endDate?: string;
  reviewStatus?: string;
}

export interface ExportHistoryItem {
  id: string;
  export_type: string;
  filter_params: Record<string, unknown>;
  record_count: number;
  filename: string;
  created_at: string;
}

export interface DashboardStats {
  totals: {
    invoices: number;
    needs_review: number;
    approved: number;
    failed_documents: number;
    processing_documents: number;
    complete_documents: number;
    batches: number;
  };
  recent_uploads: {
    document_id: string;
    filename: string;
    status: string;
    batch_id: string | null;
    created_at: string;
  }[];
  vendor_statistics: { vendor_name: string; invoice_count: number }[];
}

export interface SearchParams {
  q?: string;
  vendor?: string;
  invoiceNumber?: string;
  startDate?: string;
  endDate?: string;
  batchId?: string;
  status?: string;
  minConfidence?: number;
  skip?: number;
  limit?: number;
}

export interface SearchInvoiceItem {
  id: string;
  invoice_number: string | null;
  vendor_name: string | null;
  invoice_date: string | null;
  total_amount: string | null;
  currency: string | null;
  needs_review: boolean;
  document_status: string | null;
  batch_id: string | null;
  filename: string | null;
}

