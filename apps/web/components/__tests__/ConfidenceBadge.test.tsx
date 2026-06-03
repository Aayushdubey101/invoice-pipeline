import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConfidenceBadge } from "../ConfidenceBadge";

describe("ConfidenceBadge", () => {
  it("renders percentage", () => {
    render(<ConfidenceBadge confidence={0.87} />);
    expect(screen.getByText("87%")).toBeInTheDocument();
  });

  it("shows green for high confidence", () => {
    const { container } = render(<ConfidenceBadge confidence={0.95} />);
    expect(container.firstChild).toHaveClass("bg-green-100");
  });

  it("shows yellow for medium confidence", () => {
    const { container } = render(<ConfidenceBadge confidence={0.80} />);
    expect(container.firstChild).toHaveClass("bg-yellow-100");
  });

  it("shows red for low confidence", () => {
    const { container } = render(<ConfidenceBadge confidence={0.60} />);
    expect(container.firstChild).toHaveClass("bg-red-100");
  });

  it("boundary: 0.90 is green", () => {
    const { container } = render(<ConfidenceBadge confidence={0.90} />);
    expect(container.firstChild).toHaveClass("bg-green-100");
  });

  it("boundary: 0.75 is yellow", () => {
    const { container } = render(<ConfidenceBadge confidence={0.75} />);
    expect(container.firstChild).toHaveClass("bg-yellow-100");
  });

  it("rounds to nearest percent", () => {
    render(<ConfidenceBadge confidence={0.876} />);
    expect(screen.getByText("88%")).toBeInTheDocument();
  });

  it("has accessible title attribute", () => {
    render(<ConfidenceBadge confidence={0.82} />);
    expect(screen.getByTitle("Confidence: 82%")).toBeInTheDocument();
  });
});
