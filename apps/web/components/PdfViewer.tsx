"use client";

import { useState, useEffect, useRef } from "react";
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
  isImage?: boolean;
  highlightPage?: number | null;
  highlightBbox?: [number, number, number, number] | null;
}

export function PdfViewer({ url, className, isImage, highlightPage, highlightBbox }: PdfViewerProps) {
  const [numPages, setNumPages] = useState<number>(0);
  const [page, setPage] = useState(1);
  const [pageWidth, setPageWidth] = useState<number>(600);
  const [originalWidth, setOriginalWidth] = useState<number>(600);
  const [originalHeight, setOriginalHeight] = useState<number>(800);
  const containerRef = useRef<HTMLDivElement>(null);

  // Sync internal page with highlightPage when it changes
  useEffect(() => {
    if (highlightPage) {
      setPage(highlightPage);
    }
  }, [highlightPage]);

  // Keep the rendered page width in sync with the available container width
  // (fixes it always rendering at a hardcoded 600px regardless of viewport).
  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width) setPageWidth(Math.max(200, Math.floor(width) - 16));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  if (isImage) {
    return (
      <div className={className}>
        <div className="overflow-auto rounded-lg border bg-muted/20 flex justify-center p-2">
          {/* eslint-disable-next-line @next/next/no-img-element -- API-served file, next/image needs remotePatterns */}
          <img src={url} alt="Invoice document" className="max-w-full h-auto" />
        </div>
      </div>
    );
  }

  return (
    <div className={className}>
      <div ref={containerRef} className="overflow-auto rounded-lg border bg-muted/20">
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
          <div className="relative">
            <Page
              pageNumber={page}
              width={pageWidth}
              renderTextLayer
              renderAnnotationLayer
              onLoadSuccess={(pageInfo) => {
                setOriginalWidth(pageInfo.originalWidth);
                setOriginalHeight(pageInfo.originalHeight);
              }}
            />
            {highlightPage === page && highlightBbox && originalWidth && (
              <div 
                className="absolute border-2 border-blue-500 bg-blue-500/20 shadow-[0_0_15px_rgba(59,130,246,0.5)] transition-all duration-300"
                style={{
                  left: `${(highlightBbox[0] / originalWidth) * 100}%`,
                  top: `${(highlightBbox[1] / originalHeight) * 100}%`,
                  width: `${((highlightBbox[2] - highlightBbox[0]) / originalWidth) * 100}%`,
                  height: `${((highlightBbox[3] - highlightBbox[1]) / originalHeight) * 100}%`,
                }}
              />
            )}
          </div>
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
