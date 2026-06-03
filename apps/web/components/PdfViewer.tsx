"use client";

import { useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

interface PdfViewerProps {
  url: string;
  className?: string;
}

export function PdfViewer({ url, className }: PdfViewerProps) {
  const [numPages, setNumPages] = useState<number>(0);
  const [page, setPage] = useState(1);

  return (
    <div className={className}>
      <div className="overflow-auto rounded-lg border bg-muted/20">
        <Document
          file={url}
          onLoadSuccess={({ numPages: n }) => setNumPages(n)}
          loading={
            <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">
              Loading PDF…
            </div>
          }
          error={
            <div className="flex items-center justify-center h-64 text-red-500 text-sm">
              Failed to load PDF.
            </div>
          }
          className="flex justify-center p-2"
        >
          <Page
            pageNumber={page}
            width={600}
            renderTextLayer
            renderAnnotationLayer
          />
        </Document>
      </div>
      {numPages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <Button
            size="icon-sm"
            variant="outline"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm text-muted-foreground tabular-nums">
            {page} / {numPages}
          </span>
          <Button
            size="icon-sm"
            variant="outline"
            onClick={() => setPage((p) => Math.min(numPages, p + 1))}
            disabled={page >= numPages}
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
