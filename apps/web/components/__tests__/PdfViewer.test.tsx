import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";

// react-pdf uses canvas + pdfjs worker — mock both for unit tests
vi.mock("react-pdf", () => ({
  pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
  Document: ({ children, file, loading }: { children?: React.ReactNode; file?: string; loading?: React.ReactNode }) => (
    <div data-testid="pdf-document" data-file={file}>
      {loading}
      {children}
    </div>
  ),
  Page: ({ pageNumber }: { pageNumber: number }) => (
    <div data-testid="pdf-page" data-page={pageNumber} />
  ),
}));

// import after mock
import { PdfViewer } from "../PdfViewer";

describe("PdfViewer", () => {
  it("renders document with correct file URL", () => {
    render(<PdfViewer url="http://localhost:8000/documents/abc/file" />);
    const doc = screen.getByTestId("pdf-document");
    expect(doc).toBeInTheDocument();
    expect(doc).toHaveAttribute("data-file", "http://localhost:8000/documents/abc/file");
  });

  it("renders first page by default", () => {
    render(<PdfViewer url="http://example.com/test.pdf" />);
    const page = screen.getByTestId("pdf-page");
    expect(page).toHaveAttribute("data-page", "1");
  });

  it("applies className", () => {
    const { container } = render(
      <PdfViewer url="http://example.com/test.pdf" className="my-class" />
    );
    expect(container.firstChild).toHaveClass("my-class");
  });
});
