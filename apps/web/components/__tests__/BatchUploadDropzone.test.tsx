import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BatchUploadDropzone } from "../BatchUploadDropzone";
import { ProviderSessionProvider } from "@/contexts/ProviderSessionContext";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

function makeFile(name: string, relativePath?: string): File {
  const file = new File(["dummy content"], name, { type: "application/pdf" });
  if (relativePath) {
    Object.defineProperty(file, "webkitRelativePath", { value: relativePath, configurable: true });
  }
  return file;
}

function renderDropzone() {
  return render(
    <ProviderSessionProvider>
      <BatchUploadDropzone />
    </ProviderSessionProvider>
  );
}

describe("BatchUploadDropzone", () => {
  it("queues same-name files from different subfolders instead of collapsing them", async () => {
    const user = userEvent.setup();
    renderDropzone();

    const input = document.getElementById("file-input-folder") as HTMLInputElement;
    const files = [
      makeFile("invoice.pdf", "2024/invoice.pdf"),
      makeFile("invoice.pdf", "2025/invoice.pdf"),
    ];
    await user.upload(input, files);

    expect(screen.getByText("2 files queued")).toBeInTheDocument();
  });

  it("dedupes a true re-selection of the same file", async () => {
    const user = userEvent.setup();
    renderDropzone();

    const input = document.getElementById("file-input-single") as HTMLInputElement;
    const file = makeFile("invoice.pdf");
    await user.upload(input, [file]);
    await user.upload(input, [file]);

    expect(screen.getByText("1 file queued")).toBeInTheDocument();
  });

  it("shows a message when unsupported files are skipped", () => {
    // `accept` is only a picker-dialog hint in real browsers — not enforced on
    // programmatic/drag-drop file sets — so simulate it the same way, bypassing
    // user-event's stricter accept-filtering.
    renderDropzone();

    const input = document.getElementById("file-input-single") as HTMLInputElement;
    const badFile = new File(["x"], "malware.exe", { type: "application/x-msdownload" });
    Object.defineProperty(input, "files", { value: [badFile], configurable: true });
    fireEvent.change(input);

    expect(screen.getByText("1 unsupported file skipped")).toBeInTheDocument();
  });
});
