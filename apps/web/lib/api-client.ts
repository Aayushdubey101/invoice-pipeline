import type {
  InvoiceDetail,
  ReviewQueue,
  UploadResponse,
  Vendor,
  VendorList,
} from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface AppSettings {
  llm_provider: string;
  lm_studio_model: string;
  lm_studio_base_url: string;
  openai_model: string;
  anthropic_model: string;
  gemini_model: string;
  has_openai_key: boolean;
  has_anthropic_key: boolean;
  has_gemini_key: boolean;
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
  openai_api_key: string;
  openai_model: string;
  anthropic_api_key: string;
  anthropic_model: string;
  gemini_api_key: string;
  gemini_model: string;
  llamacpp_base_url: string;
  llamacpp_model: string;
  llamacpp_api_key: string;
  llamacpp_context_length: number;
  llamacpp_temperature: number;
  llamacpp_max_tokens: number;
  ollama_base_url: string;
  ollama_model: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData;
  const res = await fetch(`${API_BASE}${path}`, {
    headers: isFormData ? (init?.headers ?? {}) : { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    const problem = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(problem.detail ?? `HTTP ${res.status}`);
  }

  return res.json() as Promise<T>;
}

export const apiClient = {
  health: () => request<{ status: string; version: string }>("/health"),

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
  },

  llm: {
    status: () => request<{
      provider: string;
      model: string;
      endpoint: string | null;
    }>("/llm/status"),
  },
};
