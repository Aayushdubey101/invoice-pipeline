"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import {
  Layers,
  CheckCircle2,
  AlertCircle,
  Clock,
  ArrowRight,
  Upload,
  RotateCcw,
  Download,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { apiClient, type BatchSummary } from "@/lib/api-client";
import { WorkspaceGuardDialog } from "@/components/WorkspaceGuardDialog";
import { useWorkspaceSession } from "@/contexts/WorkspaceSessionContext";
import { generateDemoBatches } from "@/lib/demo-data";

function BatchStatusIndicator({ batch }: { batch: BatchSummary }) {
  if (batch.failed > 0 && batch.completed === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-red-600 text-xs">
        <AlertCircle className="h-3.5 w-3.5" /> Failed
      </span>
    );
  }
  if (batch.failed > 0) {
    return (
      <span className="inline-flex items-center gap-1 text-yellow-600 text-xs">
        <AlertCircle className="h-3.5 w-3.5" /> Partial ({batch.failed} failed)
      </span>
    );
  }
  if (batch.pending > 0) {
    return (
      <span className="inline-flex items-center gap-1 text-blue-600 text-xs">
        <Clock className="h-3.5 w-3.5" /> Pending
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-green-600 text-xs">
      <CheckCircle2 className="h-3.5 w-3.5" /> Complete
    </span>
  );
}

export default function BatchesPage() {
  const { isSignedIn } = useAuth();
  const { hasActiveWorkspace } = useWorkspaceSession();
  const hasWorkspace = hasActiveWorkspace() || isSignedIn;
  const [demoData] = useState(() => generateDemoBatches());

  const [batches, setBatches] = useState<BatchSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.batch.list();
      setBatches(data.batches);
      setTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load batches");
    } finally {
      setLoading(false);
    }
  };

  const retryFailed = async (batchId: string) => {
    setRetrying(batchId);
    setError(null);
    try {
      await apiClient.batch.retryFailed(batchId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to retry batch");
    } finally {
      setRetrying(null);
    }
  };

  useEffect(() => {
    if (hasWorkspace) load();
    else setLoading(false);
  }, [hasWorkspace]);

  const displayBatches = hasWorkspace ? batches : demoData.batches;
  const displayTotal = hasWorkspace ? total : demoData.total;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {!hasWorkspace && <WorkspaceGuardDialog open dismissible />}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Batch History</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {hasWorkspace
              ? `${displayTotal} batch${displayTotal !== 1 ? "es" : ""} total`
              : "Preview data — continue as guest for your real batches"}
          </p>
        </div>
        <Link href="/upload">
          <Button size="sm" className="gap-2">
            <Upload className="h-4 w-4" />
            New Batch
          </Button>
        </Link>
      </div>

      {hasWorkspace && error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-3 animate-pulse">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="rounded-lg border bg-card h-20" />
          ))}
        </div>
      ) : displayBatches.length === 0 ? (
        <div className="rounded-lg border bg-card p-12 text-center space-y-3">
          <Layers className="h-8 w-8 text-muted-foreground mx-auto" />
          <p className="text-muted-foreground text-sm">No batches yet</p>
          <Link href="/upload">
            <Button size="sm" variant="outline" className="gap-2">
              <Upload className="h-4 w-4" />
              Upload your first batch
            </Button>
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {displayBatches.map((batch) => (
            <div
              key={batch.batch_id}
              className="rounded-lg border bg-card hover:shadow-sm transition-shadow"
            >
              <div className="flex items-start gap-4 p-4">
                {/* Icon */}
                <div className="rounded-md bg-muted p-2 shrink-0">
                  <Layers className="h-5 w-5 text-muted-foreground" />
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0 space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-xs text-muted-foreground truncate">
                      {batch.batch_id.slice(0, 18)}…
                    </span>
                    <Badge variant="secondary" className="text-xs shrink-0">
                      {batch.upload_source}
                    </Badge>
                    <BatchStatusIndicator batch={batch} />
                  </div>

                  {/* Stats row */}
                  <div className="flex gap-4 text-xs text-muted-foreground flex-wrap">
                    <span>{batch.total_files} file{batch.total_files !== 1 ? "s" : ""}</span>
                    <span className="text-green-600">{batch.completed} completed</span>
                    {batch.failed > 0 && <span className="text-red-600">{batch.failed} failed</span>}
                    {batch.skipped > 0 && <span>{batch.skipped} skipped</span>}
                    {batch.avg_confidence != null && (
                      <span>{(batch.avg_confidence * 100).toFixed(1)}% avg. confidence</span>
                    )}
                    {batch.processing_time_ms != null && (
                      <span>{(batch.processing_time_ms / 1000).toFixed(1)}s</span>
                    )}
                  </div>

                  <p className="text-xs text-muted-foreground">
                    {new Date(batch.created_at).toLocaleString()}
                  </p>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1 shrink-0">
                  {batch.failed > 0 && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-8 gap-1.5 text-xs"
                      disabled={!hasWorkspace || retrying === batch.batch_id}
                      title={!hasWorkspace ? "Continue as guest to retry" : undefined}
                      onClick={() => retryFailed(batch.batch_id)}
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                      Retry failed
                    </Button>
                  )}
                  {hasWorkspace ? (
                    <a
                      href={apiClient.export.excel({ batchId: batch.batch_id })}
                      download
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Button size="sm" variant="ghost" className="h-8 gap-1.5 text-xs">
                        <Download className="h-3.5 w-3.5" />
                        Excel
                      </Button>
                    </a>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-8 gap-1.5 text-xs"
                      disabled
                      title="Continue as guest to export"
                    >
                      <Download className="h-3.5 w-3.5" />
                      Excel
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
