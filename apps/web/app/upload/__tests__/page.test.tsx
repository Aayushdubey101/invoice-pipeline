import { render, screen } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import UploadPage from "../page";
import { useWorkspaceSession } from "@/contexts/WorkspaceSessionContext";
import { useProviderSession } from "@/contexts/ProviderSessionContext";
import * as clerkNextjs from "@clerk/nextjs";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Mock WorkspaceSessionContext
vi.mock("@/contexts/WorkspaceSessionContext", () => ({
  useWorkspaceSession: vi.fn(),
}));

// Mock ProviderSessionContext
vi.mock("@/contexts/ProviderSessionContext", () => ({
  useProviderSession: vi.fn(),
}));

// Mock Clerk useAuth
vi.mock("@clerk/nextjs", () => {
  return {
    useAuth: vi.fn(),
  };
});

// Mock api client
vi.mock("@/lib/api-client", () => ({
  apiClient: {
    llm: {
      status: vi.fn().mockResolvedValue({ provider: "openai" }),
    },
  },
}));

// Mock components
vi.mock("@/components/BatchUploadDropzone", () => ({
  BatchUploadDropzone: () => <div data-testid="dropzone">Dropzone</div>,
}));

vi.mock("@/components/ProviderGuardDialog", () => ({
  ProviderGuardDialog: () => <div data-testid="provider-guard">Provider Guard</div>,
}));

vi.mock("@/components/WorkspaceGuardDialog", () => ({
  WorkspaceGuardDialog: () => <div data-testid="workspace-guard">Workspace Guard</div>,
}));

const queryClient = new QueryClient();

describe("UploadPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Default workspace mock (no active workspace)
    vi.mocked(useWorkspaceSession).mockReturnValue({
      hasActiveWorkspace: () => false,
      expiresAt: null,
      createWorkspace: vi.fn(),
    } as any);

    // Default provider mock
    vi.mocked(useProviderSession).mockReturnValue({
      hasSessionProvider: () => true,
    } as any);
  });

  const renderPage = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <UploadPage />
      </QueryClientProvider>
    );
  };

  it("shows workspace guard when signed out and no active workspace", async () => {
    vi.mocked(clerkNextjs.useAuth).mockReturnValue({ isSignedIn: false } as any);
    
    renderPage();
    
    expect(await screen.findByTestId("workspace-guard")).toBeInTheDocument();
    expect(screen.queryByTestId("dropzone")).not.toBeInTheDocument();
  });

  it("shows dropzone when signed in, even if no active guest workspace", async () => {
    vi.mocked(clerkNextjs.useAuth).mockReturnValue({ isSignedIn: true } as any);
    
    renderPage();
    
    expect(screen.queryByTestId("workspace-guard")).not.toBeInTheDocument();
    // It should render dropzone instead
    expect(await screen.findByTestId("dropzone")).toBeInTheDocument();
  });
});
