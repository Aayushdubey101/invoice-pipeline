import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FinishSessionDialog } from "../FinishSessionDialog";
import { apiClient } from "@/lib/api-client";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

const clearWorkspace = vi.fn();
vi.mock("@/contexts/WorkspaceSessionContext", () => ({
  useWorkspaceSession: () => ({ clearWorkspace }),
}));

const resetSession = vi.fn();
vi.mock("@/contexts/ProviderSessionContext", () => ({
  useProviderSession: () => ({ resetSession }),
}));

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    session: {
      finish: vi.fn(),
    },
  },
}));

describe("FinishSessionDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    URL.createObjectURL = vi.fn(() => "blob:mock");
    URL.revokeObjectURL = vi.fn();
  });

  it("shows a confirm step with Cancel and does not call finish until confirmed", () => {
    render(<FinishSessionDialog open onOpenChange={vi.fn()} />);

    expect(screen.getByText("End Guest Session?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(apiClient.session.finish).not.toHaveBeenCalled();
  });

  it("closes without downloading or purging when Cancel is clicked", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(<FinishSessionDialog open onOpenChange={onOpenChange} />);

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(apiClient.session.finish).not.toHaveBeenCalled();
    expect(clearWorkspace).not.toHaveBeenCalled();
  });

  it("closes without downloading when the X button is clicked", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(<FinishSessionDialog open onOpenChange={onOpenChange} />);

    await user.click(screen.getByRole("button", { name: "Close" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(apiClient.session.finish).not.toHaveBeenCalled();
  });

  it("only calls finish() after Download & Finish is clicked", async () => {
    const user = userEvent.setup();
    vi.mocked(apiClient.session.finish).mockResolvedValue(new Blob(["zip"]));
    render(<FinishSessionDialog open onOpenChange={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Download & Finish" }));

    await waitFor(() => expect(apiClient.session.finish).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/download has started/)).toBeInTheDocument();
  });

  it("resets session and navigates home when Done is clicked after a successful export", async () => {
    const user = userEvent.setup();
    vi.mocked(apiClient.session.finish).mockResolvedValue(new Blob(["zip"]));
    const onOpenChange = vi.fn();
    render(<FinishSessionDialog open onOpenChange={onOpenChange} />);

    await user.click(screen.getByRole("button", { name: "Download & Finish" }));
    await user.click(await screen.findByRole("button", { name: "Done" }));

    expect(resetSession).toHaveBeenCalled();
    expect(clearWorkspace).toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(push).toHaveBeenCalledWith("/");
  });
});
