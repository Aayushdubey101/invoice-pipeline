import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { WorkspaceGuardDialog } from "../WorkspaceGuardDialog";

vi.mock("@/contexts/WorkspaceSessionContext", () => ({
  useWorkspaceSession: () => ({ createWorkspace: vi.fn() }),
}));

describe("WorkspaceGuardDialog", () => {
  it("shows the start-session message and guest CTA when open", () => {
    render(<WorkspaceGuardDialog open />);

    expect(screen.getByText("Start a Session to Continue")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue as Guest" })).toBeInTheDocument();
  });

  it("renders nothing visible when closed", () => {
    render(<WorkspaceGuardDialog open={false} />);

    expect(screen.queryByText("Start a Session to Continue")).not.toBeInTheDocument();
  });
});
