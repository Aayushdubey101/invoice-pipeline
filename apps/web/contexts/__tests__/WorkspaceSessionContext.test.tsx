import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { WorkspaceSessionProvider, useWorkspaceSession } from "../WorkspaceSessionContext";

const STORAGE_KEY = "invoice_pipeline_workspace_session";

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    workspaces: {
      create: vi.fn().mockResolvedValue({
        id: "ws-test-123",
        workspace_type: "guest",
        status: "active",
        expires_at: "2099-01-01T00:00:00Z",
        created_at: "2026-01-01T00:00:00Z",
      }),
    },
  },
  setWorkspaceId: vi.fn(),
}));

function Consumer() {
  const { workspaceId, hasActiveWorkspace, createWorkspace, clearWorkspace } = useWorkspaceSession();
  return (
    <div>
      <span data-testid="workspace-id">{workspaceId ?? "none"}</span>
      <span data-testid="has-workspace">{String(hasActiveWorkspace())}</span>
      <button onClick={() => createWorkspace()}>create</button>
      <button onClick={() => clearWorkspace()}>clear</button>
    </div>
  );
}

describe("WorkspaceSessionContext", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.clearAllMocks();
  });

  it("creates a workspace, persists it to sessionStorage, and clears it", async () => {
    render(
      <WorkspaceSessionProvider>
        <Consumer />
      </WorkspaceSessionProvider>
    );

    expect(screen.getByTestId("has-workspace")).toHaveTextContent("false");

    fireEvent.click(screen.getByText("create"));

    expect(await screen.findByTestId("workspace-id")).toHaveTextContent("ws-test-123");
    expect(screen.getByTestId("has-workspace")).toHaveTextContent("true");

    await waitFor(() => {
      const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "{}");
      expect(stored.workspaceId).toBe("ws-test-123");
    });

    fireEvent.click(screen.getByText("clear"));

    expect(await screen.findByTestId("workspace-id")).toHaveTextContent("none");
    expect(screen.getByTestId("has-workspace")).toHaveTextContent("false");
  });

  it("hydrates an active workspace from an existing sessionStorage value on mount", async () => {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ workspaceId: "ws-hydrated", expiresAt: "2099-01-01T00:00:00Z" })
    );

    render(
      <WorkspaceSessionProvider>
        <Consumer />
      </WorkspaceSessionProvider>
    );

    expect(await screen.findByTestId("workspace-id")).toHaveTextContent("ws-hydrated");
    expect(screen.getByTestId("has-workspace")).toHaveTextContent("true");
  });

  it("treats an expired stored workspace as inactive", async () => {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ workspaceId: "ws-expired", expiresAt: "2020-01-01T00:00:00Z" })
    );

    render(
      <WorkspaceSessionProvider>
        <Consumer />
      </WorkspaceSessionProvider>
    );

    expect(await screen.findByTestId("has-workspace")).toHaveTextContent("false");
  });
});
