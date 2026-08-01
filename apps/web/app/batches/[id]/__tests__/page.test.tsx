import React from "react";
import { render, screen } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import BatchDetailPage from "../page";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("react", async (importOriginal) => {
  const actual: any = await importOriginal();
  return {
    ...actual,
    use: (promiseOrContext: any) => {
      if (promiseOrContext instanceof Promise) {
        // Just cheat and return the value we know we gave it
        return { id: "test-batch" };
      }
      return actual.use(promiseOrContext);
    },
  };
});

// Mock api client
const mockBatchGet = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: {
    batch: {
      get: (...args: any[]) => mockBatchGet(...args),
    },
  },
}));

// Mock lucide icons
vi.mock("lucide-react", () => ({
  ArrowLeft: () => <div data-testid="icon-arrow-left" />,
  FileText: () => <div data-testid="icon-file-text" />,
  Loader2: () => <div data-testid="icon-loader" />,
}));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
});

describe("BatchDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryClient.clear();
  });

  const renderPage = (id: string = "test-batch") => {
    return render(
      <QueryClientProvider client={queryClient}>
        <React.Suspense fallback={<div>Loading...</div>}>
          <BatchDetailPage params={Promise.resolve({ id })} />
        </React.Suspense>
      </QueryClientProvider>
    );
  };

  it("renders error message for a failed document", async () => {
    mockBatchGet.mockResolvedValue({
      batch_id: "test-batch",
      upload_source: "web",
      total_files: 1,
      completed: 0,
      failed: 1,
      skipped: 0,
      pending: 0,
      avg_confidence: null,
      processing_time_ms: 100,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      documents: [
        {
          document_id: "doc-1",
          filename: "bad.pdf",
          status: "failed",
          errors: [
            {
              stage: "extract",
              error_type: "processing_error",
              message: "Corrupted PDF file",
              fatal: true,
            }
          ]
        }
      ]
    });

    renderPage();

    // Verify the error message renders
    expect(await screen.findByText("Corrupted PDF file")).toBeInTheDocument();
  });
});
