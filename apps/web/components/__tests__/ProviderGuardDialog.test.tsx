import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
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
});
