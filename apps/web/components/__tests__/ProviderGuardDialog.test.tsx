import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProviderGuardDialog } from "../ProviderGuardDialog";

describe("ProviderGuardDialog", () => {
  it("shows the no-provider message and both action links when open", () => {
    render(<ProviderGuardDialog open />);

    expect(screen.getByText("No AI Provider Configured")).toBeInTheDocument();
    expect(
      screen.getByText(/To process documents you must configure an AI Provider/)
    ).toBeInTheDocument();

    const docsLink = screen.getByRole("link", { name: "Open Documentation" });
    expect(docsLink).toHaveAttribute("href", "/docs");

    const settingsLink = screen.getByRole("link", { name: "Configure Provider" });
    expect(settingsLink).toHaveAttribute("href", "/settings");
  });

  it("renders nothing visible when closed", () => {
    render(<ProviderGuardDialog open={false} />);

    expect(screen.queryByText("No AI Provider Configured")).not.toBeInTheDocument();
  });

  it("has no close button when not dismissible", () => {
    render(<ProviderGuardDialog open />);

    expect(screen.queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
  });

  it("closes via the X button when dismissible", async () => {
    const user = userEvent.setup();
    render(<ProviderGuardDialog open dismissible />);

    await user.click(screen.getByRole("button", { name: "Close" }));

    expect(screen.queryByText("No AI Provider Configured")).not.toBeInTheDocument();
  });
});
