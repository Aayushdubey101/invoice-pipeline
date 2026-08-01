"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Upload,
  FolderOpen,
  FileText,
  AlertCircle,
  Loader2,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api-client";
import { useProviderSession } from "@/contexts/ProviderSessionContext";

const IN_PROGRESS_BATCH_KEY = "invoice_pipeline_in_progress_batch_id";

const ACCEPTED_MIME = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/tiff",
  "image/x-tiff",
];
const ACCEPTED_EXT = ".pdf,.png,.jpg,.jpeg,.tiff,.tif";

type UploadMode = "single" | "batch";
type UploadState = "idle" | "uploading" | "success" | "error";

/** Files sharing a name in different subfolders must not collapse into one. */
function fileKey(f: File): string {
  const relPath = (f as File & { webkitRelativePath?: string }).webkitRelativePath;
  return `${relPath || f.name}:${f.size}`;
}

function readAllEntries(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  return new Promise((resolve, reject) => {
    const all: FileSystemEntry[] = [];
    const readBatch = () => {
      reader.readEntries((batch) => {
        if (batch.length === 0) {
          resolve(all);
        } else {
          all.push(...batch);
          readBatch();
        }
      }, reject);
    };
    readBatch();
  });
}

/** Recursively walk a dropped folder entry, tagging files with their relative path. */
async function traverseEntry(entry: FileSystemEntry, out: File[]): Promise<void> {
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) =>
      (entry as FileSystemFileEntry).file(resolve, reject)
    );
    Object.defineProperty(file, "webkitRelativePath", {
      value: entry.fullPath.replace(/^\//, ""),
      configurable: true,
    });
    out.push(file);
  } else if (entry.isDirectory) {
    const entries = await readAllEntries((entry as FileSystemDirectoryEntry).createReader());
    for (const child of entries) {
      await traverseEntry(child, out);
    }
  }
}

export function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, string> = {
    complete: "bg-green-100 text-green-700 border-green-200",
    needs_review: "bg-yellow-100 text-yellow-700 border-yellow-200",
    failed: "bg-red-100 text-red-700 border-red-200",
    skipped: "bg-gray-100 text-gray-600 border-gray-200",
    processing: "bg-blue-100 text-blue-700 border-blue-200",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium border",
        variants[status] ?? "bg-gray-100 text-gray-600 border-gray-200"
      )}
    >
      {status.replace("_", " ")}
    </span>
  );
}

export function BatchUploadDropzone() {
  const router = useRouter();
  const { activeProvider, providers, hasSessionProvider } = useProviderSession();
  const [dragOver, setDragOver] = useState(false);
  const [state, setState] = useState<UploadState>("idle");
  const [files, setFiles] = useState<File[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [skippedMsg, setSkippedMsg] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [resumeBatchId, setResumeBatchId] = useState<string | null>(null);
  const singleInputRef = useRef<HTMLInputElement>(null);
  const multiInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // A refresh/navigation mid-upload used to lose all trace of the batch —
  // the backend now returns batch_id immediately, so check for one left
  // in flight and offer to resume watching it instead of showing nothing.
  useEffect(() => {
    const storedId = localStorage.getItem(IN_PROGRESS_BATCH_KEY);
    if (!storedId) return;
    apiClient.batch
      .get(storedId)
      .then((batch) => {
        const done = batch.completed + batch.failed + batch.skipped >= batch.total_files;
        if (done) {
          localStorage.removeItem(IN_PROGRESS_BATCH_KEY);
        } else {
          setResumeBatchId(storedId);
        }
      })
      .catch(() => localStorage.removeItem(IN_PROGRESS_BATCH_KEY));
  }, []);

  const reset = () => {
    setState("idle");
    setFiles([]);
    setErrorMsg(null);
    setSkippedMsg(null);
    setUploadProgress(0);
  };

  const addFiles = (incoming: FileList | File[]) => {
    const arr = Array.from(incoming);
    const accepted = arr.filter(
      (f) => ACCEPTED_MIME.includes(f.type) || f.name.match(/\.(pdf|png|jpe?g|tiff?)$/i)
    );
    const skippedCount = arr.length - accepted.length;
    setSkippedMsg(
      skippedCount > 0 ? `${skippedCount} unsupported file${skippedCount !== 1 ? "s" : ""} skipped` : null
    );
    setFiles((prev) => {
      const keys = new Set(prev.map(fileKey));
      return [...prev, ...accepted.filter((f) => !keys.has(fileKey(f)))];
    });
  };

  const removeFile = (idx: number) =>
    setFiles((prev) => prev.filter((_, i) => i !== idx));

  const uploadAll = useCallback(async () => {
    if (!files.length) return;
    setState("uploading");
    setErrorMsg(null);
    setUploadProgress(0);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const sessionProvider = hasSessionProvider() && activeProvider ? providers[activeProvider] : undefined;
      const res = await apiClient.batch.upload(files, "web", {
        onProgress: setUploadProgress,
        signal: controller.signal,
        providerHeaders:
          sessionProvider && activeProvider
            ? {
                provider: activeProvider,
                apiKey: sessionProvider.apiKey,
                model: sessionProvider.model,
                config: sessionProvider.config,
              }
            : undefined,
      });
      localStorage.setItem(IN_PROGRESS_BATCH_KEY, res.batch_id);
      router.push(`/batches/${res.batch_id}`);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setState("idle");
      } else {
        setErrorMsg(err instanceof Error ? err.message : "Upload failed");
        setState("error");
      }
    } finally {
      abortRef.current = null;
    }
  }, [files, activeProvider, providers, hasSessionProvider]);

  const cancelUpload = () => abortRef.current?.abort();

  const onDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    const items = e.dataTransfer.items;
    const entries =
      items && items.length && typeof items[0].webkitGetAsEntry === "function"
        ? Array.from(items)
            .map((item) => item.webkitGetAsEntry())
            .filter((entry): entry is FileSystemEntry => entry !== null)
        : [];
    if (entries.length) {
      void (async () => {
        const collected: File[] = [];
        for (const entry of entries) {
          await traverseEntry(entry, collected);
        }
        if (collected.length) addFiles(collected);
      })();
      return;
    }
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  }, []);

  // ── Idle / uploading state ─────────────────────────────────────────────────
  return (
    <div className="space-y-4">
      {/* Resume banner — a batch from before a refresh/navigation is still processing */}
      {resumeBatchId && state === "idle" && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-300">
          <span className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            A batch is still processing in the background.
          </span>
          <Link href={`/batches/${resumeBatchId}`} className="underline font-medium shrink-0">
            View progress
          </Link>
        </div>
      )}

      {/* Drop zone */}
      <div
        role="button"
        tabIndex={0}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && state !== "uploading")
            singleInputRef.current?.click();
        }}
        onClick={() => state !== "uploading" && singleInputRef.current?.click()}
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
            Drop files here, or{" "}
            <span className="text-primary underline-offset-2 hover:underline">browse</span>
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            PDF, PNG, JPEG, TIFF — max 50 MB per file
          </p>
        </div>

        {/* Hidden inputs */}
        <input
          ref={singleInputRef}
          id="file-input-single"
          type="file"
          className="sr-only"
          accept={ACCEPTED_EXT}
          multiple
          onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }}
          onClick={(e) => e.stopPropagation()}
          disabled={state === "uploading"}
        />
      </div>

      {/* Folder upload button */}
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          disabled={state === "uploading"}
          onClick={() => multiInputRef.current?.click()}
        >
          <FolderOpen className="h-4 w-4" />
          Select Folder
        </Button>
        <input
          ref={multiInputRef}
          id="file-input-folder"
          type="file"
          className="sr-only"
          accept={ACCEPTED_EXT}
          multiple
          // @ts-expect-error – webkitdirectory is not in React's types but works in all modern browsers
          webkitdirectory=""
          onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }}
          disabled={state === "uploading"}
        />
      </div>

      {/* File queue */}
      {files.length > 0 && (
        <div className="rounded-lg border divide-y text-sm overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 bg-muted/40">
            <span className="font-medium">
              {files.length} file{files.length !== 1 ? "s" : ""} queued
            </span>
            <button
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={() => setFiles([])}
              disabled={state === "uploading"}
            >
              Clear all
            </button>
          </div>
          {files.slice(0, 10).map((f, i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-2">
              <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="truncate flex-1">{f.name}</span>
              <span className="text-xs text-muted-foreground shrink-0">
                {(f.size / 1024).toFixed(0)} KB
              </span>
              {state !== "uploading" && (
                <button
                  onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                  className="text-muted-foreground hover:text-red-500 transition-colors"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          ))}
          {files.length > 10 && (
            <div className="px-4 py-2 text-xs text-muted-foreground">
              + {files.length - 10} more files
            </div>
          )}
        </div>
      )}

      {/* Upload / status */}
      {state === "uploading" ? (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              Uploading {files.length} file{files.length !== 1 ? "s" : ""}… {uploadProgress}%
            </span>
            <button
              className="text-xs text-muted-foreground hover:text-red-500 transition-colors"
              onClick={cancelUpload}
            >
              Cancel
            </button>
          </div>
          <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
            <div
              className="h-full bg-primary transition-all"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            Cancelling stops waiting for a response; files already sent may still finish processing on the server.
          </p>
        </div>
      ) : (
        files.length > 0 && (
          <Button onClick={uploadAll} className="gap-2">
            <Upload className="h-4 w-4" />
            Process {files.length} file{files.length !== 1 ? "s" : ""}
          </Button>
        )
      )}

      {/* Skipped files */}
      {skippedMsg && (
        <div className="flex items-center gap-2 rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-2 text-xs text-yellow-800 dark:border-yellow-900 dark:bg-yellow-950 dark:text-yellow-300">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          {skippedMsg}
        </div>
      )}

      {/* Error */}
      {state === "error" && errorMsg && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {errorMsg}
        </div>
      )}
    </div>
  );
}
