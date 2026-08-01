"use client";

import { use, useEffect } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { apiClient, type BatchDetail } from "@/lib/api-client";
import { StatusBadge } from "@/components/BatchUploadDropzone";

const IN_PROGRESS_BATCH_KEY = "invoice_pipeline_in_progress_batch_id";

function isDone(batch: BatchDetail): boolean {
  return batch.completed + batch.failed + batch.skipped >= batch.total_files;
}

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function BatchDetailPage({ params }: PageProps) {
  const { id } = use(params);

  const { data: batch, isLoading, isError } = useQuery({
    queryKey: ["batch", id],
    queryFn: () => apiClient.batch.get(id),
    refetchInterval: (query) => {
      const data = query.state.data as BatchDetail | undefined;
      return data && isDone(data) ? false : 1500;
    },
  });

  useEffect(() => {
    if (batch && isDone(batch) && localStorage.getItem(IN_PROGRESS_BATCH_KEY) === id) {
      localStorage.removeItem(IN_PROGRESS_BATCH_KEY);
    }
  }, [batch, id]);

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto space-y-4">
        <div className="h-8 w-48 rounded bg-muted animate-pulse" />
        <div className="h-40 rounded-lg border bg-muted/20 animate-pulse" />
      </div>
    );
  }

  if (isError || !batch) {
    return (
      <div className="max-w-3xl mx-auto space-y-4">
        <Link href="/batches" className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "gap-1")}>
          <ArrowLeft className="h-4 w-4" /> Batch History
        </Link>
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          Batch not found.
        </div>
      </div>
    );
  }

  const done = isDone(batch);
  const processed = batch.completed + batch.failed + batch.skipped;
  const percent = batch.total_files > 0 ? Math.round((processed / batch.total_files) * 100) : 0;

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <Link href="/batches" className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "gap-1")}>
        <ArrowLeft className="h-4 w-4" /> Batch History
      </Link>

      <div className="rounded-lg border bg-card p-5 space-y-3">
        <div className="flex items-center gap-2">
          {!done && <Loader2 className="h-4 w-4 animate-spin text-blue-600" />}
          <span className="font-semibold">
            {done ? "Batch complete" : "Processing…"} — {processed} of {batch.total_files} files
          </span>
        </div>

        <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
          <div
            className={cn("h-full transition-all", done ? "bg-green-500" : "bg-primary")}
            style={{ width: `${percent}%` }}
          />
        </div>

        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
          <span className="text-muted-foreground">Batch ID</span>
          <span className="font-mono text-xs truncate">{batch.batch_id}</span>
          <span className="text-muted-foreground">Completed</span>
          <span className="text-green-700 font-medium">{batch.completed}</span>
          {batch.failed > 0 && (
            <>
              <span className="text-muted-foreground">Failed</span>
              <span className="text-red-600 font-medium">{batch.failed}</span>
            </>
          )}
          {batch.skipped > 0 && (
            <>
              <span className="text-muted-foreground">Skipped</span>
              <span>{batch.skipped}</span>
            </>
          )}
          {batch.avg_confidence != null && (
            <>
              <span className="text-muted-foreground">Avg. Confidence</span>
              <span>{(batch.avg_confidence * 100).toFixed(1)}%</span>
            </>
          )}
        </div>
      </div>

      {batch.documents.length > 0 && (
        <div className="rounded-lg border divide-y text-sm overflow-hidden">
          {batch.documents.map((d) => (
            <div key={d.document_id} className="flex flex-col">
              <div className="flex items-center gap-3 px-4 py-2">
                <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="truncate flex-1">{d.filename}</span>
                <StatusBadge status={d.status} />
              </div>
              {d.status === "failed" && d.errors && d.errors.length > 0 && (
                <div className="mx-4 mb-3 mt-1 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
                  {d.errors.find(e => e.fatal)?.message || d.errors[0]?.message}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {done && (
        <div className="flex gap-2">
          <Link href="/review">
            <Button size="sm">Review Queue</Button>
          </Link>
          <Link href="/upload">
            <Button size="sm" variant="outline">Upload More</Button>
          </Link>
        </div>
      )}
    </div>
  );
}
