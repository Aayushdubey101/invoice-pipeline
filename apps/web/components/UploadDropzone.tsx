"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Upload, FileText, AlertCircle, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api-client";
import type { UploadResponse } from "@/lib/types";

const ACCEPTED_MIME = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/tiff",
  "message/rfc822",
  "text/plain",
];

type UploadState = "idle" | "uploading" | "success" | "error";

export function UploadDropzone() {
  const router = useRouter();
  const [dragOver, setDragOver] = useState(false);
  const [state, setState] = useState<UploadState>("idle");
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const openBrowse = () => inputRef.current?.click();

  const upload = useCallback(async (f: File) => {
    setFile(f);
    setState("uploading");
    setErrorMsg(null);
    try {
      const res = await apiClient.documents.upload(f);
      setResult(res);
      setState("success");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Upload failed");
      setState("error");
    }
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(false);
      const dropped = e.dataTransfer.files[0];
      if (dropped) upload(dropped);
    },
    [upload]
  );

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files?.[0];
    if (picked) upload(picked);
  };

  if (state === "success" && result) {
    return (
      <div className="rounded-lg border border-green-200 bg-green-50 p-6 space-y-3 dark:border-green-900 dark:bg-green-950">
        <div className="flex items-center gap-2 text-green-700 dark:text-green-300">
          <CheckCircle2 className="h-5 w-5" />
          <span className="font-medium">Upload complete</span>
        </div>
        <dl className="text-sm space-y-1">
          <div className="flex gap-2">
            <dt className="text-muted-foreground w-28">Document ID</dt>
            <dd className="font-mono text-xs truncate">{result.document_id}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-muted-foreground w-28">Status</dt>
            <dd className="capitalize">{result.status}</dd>
          </div>
          {result.errors.length > 0 && (
            <div className="flex gap-2">
              <dt className="text-muted-foreground w-28">Errors</dt>
              <dd className="text-red-600">{result.errors.length} stage error(s)</dd>
            </div>
          )}
        </dl>
        <div className="flex gap-2 pt-1">
          <Button
            size="sm"
            onClick={() => router.push(`/review`)}
          >
            View Review Queue
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setState("idle");
              setResult(null);
              setFile(null);
            }}
          >
            Upload Another
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div
        role="button"
        tabIndex={0}
        onClick={() => {
          if (state !== "uploading") openBrowse();
        }}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            openBrowse();
          }
        }}
        className={cn(
          "flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-10 transition-colors cursor-pointer",
          dragOver
            ? "border-primary bg-primary/5"
            : "border-border hover:border-primary/50 hover:bg-muted/30"
        )}
      >
        <Upload className={cn("h-10 w-10", dragOver ? "text-primary" : "text-muted-foreground")} />
        <div className="text-center">
          <p className="text-sm font-medium">
            {state === "uploading" ? (
              <span className="text-muted-foreground animate-pulse">Uploading {file?.name}…</span>
            ) : (
              <>
                Drop a file here, or{" "}
                <span className="text-primary underline-offset-2 hover:underline">
                  browse
                </span>
              </>
            )}
          </p>
          <p className="text-xs text-muted-foreground mt-1">PDF, PNG, JPEG, TIFF, EML — max 50 MB</p>
        </div>
        <input
          ref={inputRef}
          id="file-input"
          type="file"
          className="sr-only"
          accept={ACCEPTED_MIME.join(",")}
          onChange={(e) => {
            onFileChange(e);
            e.target.value = "";
          }}
          onClick={(e) => e.stopPropagation()}
          disabled={state === "uploading"}
        />
      </div>

      {state === "error" && errorMsg && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {errorMsg}
        </div>
      )}

      {state === "uploading" && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground px-1">
          <FileText className="h-4 w-4" />
          <span className="truncate">{file?.name}</span>
          <span className="ml-auto animate-pulse">Processing…</span>
        </div>
      )}
    </div>
  );
}
