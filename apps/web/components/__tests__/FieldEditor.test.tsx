import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FieldEditor } from "../FieldEditor";
import type { InvoiceField } from "@/lib/types";

function makeField(overrides: Partial<InvoiceField> = {}): InvoiceField {
  return {
    id: "f1",
    field_name: "invoice_number",
    raw_value: "INV-001",
    canonical_value: "INV-001",
    confidence: 0.9,
    evidence: "Invoice Number: INV-001",
    needs_review: false,
    reviewed: false,
    reviewed_value: null,
    page: null,
    bbox: null,
    ...overrides,
  };
}

describe("FieldEditor", () => {
  it("renders field name and value", () => {
    render(<FieldEditor field={makeField()} onSave={vi.fn()} />);
    expect(screen.getByText("invoice number")).toBeInTheDocument();
    expect(screen.getByText("INV-001")).toBeInTheDocument();
  });

  it("shows evidence snippet", () => {
    render(<FieldEditor field={makeField()} onSave={vi.fn()} />);
    expect(screen.getByText(/"Invoice Number: INV-001"/)).toBeInTheDocument();
  });

  it("shows edit input on edit button click", async () => {
    const user = userEvent.setup();
    render(<FieldEditor field={makeField()} onSave={vi.fn()} />);
    const editBtn = screen.getByLabelText("Edit invoice_number");
    await user.click(editBtn);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("calls onSave with edited value", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<FieldEditor field={makeField()} onSave={onSave} />);
    await user.click(screen.getByLabelText("Edit invoice_number"));
    const input = screen.getByRole("textbox");
    await user.clear(input);
    await user.type(input, "INV-999");
    await user.click(screen.getByLabelText("Save"));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith("f1", "INV-999"));
  });

  it("cancels edit on cancel button click", async () => {
    const user = userEvent.setup();
    render(<FieldEditor field={makeField()} onSave={vi.fn()} />);
    await user.click(screen.getByLabelText("Edit invoice_number"));
    await user.click(screen.getByLabelText("Cancel"));
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("saves on Enter key", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<FieldEditor field={makeField()} onSave={onSave} />);
    await user.click(screen.getByLabelText("Edit invoice_number"));
    await user.keyboard("{Enter}");
    await waitFor(() => expect(onSave).toHaveBeenCalled());
  });

  it("cancels on Escape key", async () => {
    const user = userEvent.setup();
    render(<FieldEditor field={makeField()} onSave={vi.fn()} />);
    await user.click(screen.getByLabelText("Edit invoice_number"));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("shows yellow background when needs_review and not reviewed", () => {
    const { container } = render(
      <FieldEditor field={makeField({ needs_review: true, reviewed: false })} onSave={vi.fn()} />
    );
    expect(container.firstChild).toHaveClass("bg-yellow-50");
  });

  it("shows reviewed label when field.reviewed is true", () => {
    render(<FieldEditor field={makeField({ reviewed: true })} onSave={vi.fn()} />);
    expect(screen.getByText("✓ reviewed")).toBeInTheDocument();
  });

  it("displays reviewed_value when set", () => {
    render(
      <FieldEditor
        field={makeField({ reviewed_value: "INV-CORRECTED" })}
        onSave={vi.fn()}
      />
    );
    expect(screen.getByText("INV-CORRECTED")).toBeInTheDocument();
  });

  it("shows dash for null value", () => {
    render(
      <FieldEditor
        field={makeField({ raw_value: null, canonical_value: null, reviewed_value: null })}
        onSave={vi.fn()}
      />
    );
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
