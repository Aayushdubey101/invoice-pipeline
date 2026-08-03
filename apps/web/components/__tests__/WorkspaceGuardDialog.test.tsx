import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

  it("has no close button when not dismissible", () => {
    render(<WorkspaceGuardDialog open />);

    expect(screen.queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
  });

  it("closes via the X button when dismissible", async () => {
    const user = userEvent.setup();
    render(<WorkspaceGuardDialog open dismissible />);

    await user.click(screen.getByRole("button", { name: "Close" }));

    expect(screen.queryByText("Start a Session to Continue")).not.toBeInTheDocument();
  });
});
