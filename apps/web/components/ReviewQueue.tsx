"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { AlertTriangle, CheckCircle2, Clock, XCircle, ChevronRight, CheckSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import type { ReviewQueueItem } from "@/lib/types";
import { WorkspaceGuardDialog } from "@/components/WorkspaceGuardDialog";
import { useWorkspaceSession } from "@/contexts/WorkspaceSessionContext";
import { generateDemoReviewQueue } from "@/lib/demo-data";

const STATUS_ICON: Record<string, React.ReactNode> = {
  complete: <CheckCircle2 className="h-4 w-4 text-green-500" />,
  failed: <XCircle className="h-4 w-4 text-red-500" />,
  needs_review: <AlertTriangle className="h-4 w-4 text-yellow-500" />,
  pending: <Clock className="h-4 w-4 text-muted-foreground" />,
  processing: <Clock className="h-4 w-4 text-blue-500 animate-spin" />,
};

function QueueRow({
  item,
  isSelected,
  onToggleSelect,
  isDemo = false,
}: {
  item: ReviewQueueItem;
  isSelected: boolean;
  onToggleSelect: () => void;
  isDemo?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 rounded-lg border bg-card hover:bg-muted/40 transition-colors group">
      <input
        type="checkbox"
        className="w-4 h-4 rounded border-gray-300"
        checked={isSelected}
        onChange={onToggleSelect}
        disabled={isDemo}
      />
      <Link
        href={`/review/${item.id}`}
        onClick={(e) => { if (isDemo) e.preventDefault(); }}
        title={isDemo ? "Continue as guest to open" : undefined}
        className={cn("flex flex-1 items-center gap-4 min-w-0", isDemo && "cursor-default")}
      >
      <div className="shrink-0">{STATUS_ICON[item.document_status] ?? STATUS_ICON.pending}</div>
      <div className="flex-1 min-w-0 space-y-0.5">
        <p className="text-sm font-medium truncate">{item.filename}</p>
        <p className="text-xs text-muted-foreground truncate">
          {item.vendor_name ?? "Unknown vendor"}
          {item.invoice_date ? ` · ${item.invoice_date}` : ""}
          {item.invoice_number ? ` · #${item.invoice_number}` : ""}
        </p>
        {item.review_reasons.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-0.5">
            {item.review_reasons.slice(0, 3).map((r) => (
              <span
                key={r}
                className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300"
              >
                {r}
              </span>
            ))}
            {item.review_reasons.length > 3 && (
              <span className="text-[10px] text-muted-foreground">
                +{item.review_reasons.length - 3} more
              </span>
            )}
          </div>
        )}
      </div>
      <div className="shrink-0 text-right">
        {item.total_amount && (
          <p className="text-sm font-medium">
            {item.currency ?? ""} {item.total_amount}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          {new Date(item.created_at).toLocaleDateString()}
        </p>
      </div>
      <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0 group-hover:text-foreground transition-colors" />
      </Link>
    </div>
  );
}

export function ReviewQueue() {
  const { isSignedIn } = useAuth();
  const { hasActiveWorkspace } = useWorkspaceSession();
  const hasWorkspace = hasActiveWorkspace() || isSignedIn;
  const [demoQueue] = useState(() => generateDemoReviewQueue());

  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const queryClient = useQueryClient();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["review-queue"],
    queryFn: () => apiClient.review.queue(),
    enabled: hasWorkspace,
  });

  const batchApproveMutation = useMutation({
    mutationFn: async (ids: string[]) => {
      await Promise.all(ids.map(id => apiClient.review.approve(id)));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      setSelectedIds(new Set());
    }
  });

  const batchRejectMutation = useMutation({
    mutationFn: async (ids: string[]) => {
      await Promise.all(ids.map(id => apiClient.review.reject(id)));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      setSelectedIds(new Set());
    }
  });

  const items = hasWorkspace ? data?.items ?? [] : demoQueue.items;
  const stats = {
    total: items.length,
    needsReview: items.filter(i => i.document_status === 'needs_review').length,
    pending: items.filter(i => i.document_status === 'pending' || i.document_status === 'processing').length,
    complete: items.filter(i => i.document_status === 'complete').length,
  };

  const filtered = search
    ? items.filter(
        (i) =>
          i.filename.toLowerCase().includes(search.toLowerCase()) ||
          i.vendor_name?.toLowerCase().includes(search.toLowerCase()) ||
          i.invoice_number?.toLowerCase().includes(search.toLowerCase())
      )
    : items;

  const toggleAll = () => {
    if (selectedIds.size === filtered.length && filtered.length > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filtered.map(i => i.id)));
    }
  };

  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  };

  const isMutating = batchApproveMutation.isPending || batchRejectMutation.isPending;

  return (
    <div className="space-y-4">
      {!hasWorkspace && <WorkspaceGuardDialog open dismissible />}
      {/* Review Statistics */}
      {(!hasWorkspace || (!isLoading && !isError)) && (
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="bg-card rounded-lg border p-3 flex flex-col justify-center">
            <span className="text-muted-foreground text-xs font-medium uppercase tracking-wider">Total</span>
            <span className="text-2xl font-semibold">{stats.total}</span>
          </div>
          <div className="bg-card rounded-lg border p-3 flex flex-col justify-center">
            <span className="text-yellow-600 dark:text-yellow-500 text-xs font-medium uppercase tracking-wider">Needs Review</span>
            <span className="text-2xl font-semibold">{stats.needsReview}</span>
          </div>
          <div className="bg-card rounded-lg border p-3 flex flex-col justify-center">
            <span className="text-blue-600 dark:text-blue-500 text-xs font-medium uppercase tracking-wider">Processing</span>
            <span className="text-2xl font-semibold">{stats.pending}</span>
          </div>
          <div className="bg-card rounded-lg border p-3 flex flex-col justify-center">
            <span className="text-green-600 dark:text-green-500 text-xs font-medium uppercase tracking-wider">Complete</span>
            <span className="text-2xl font-semibold">{stats.complete}</span>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 flex-1 min-w-[300px]">
          <input
            type="search"
            placeholder="Search by filename, vendor, invoice #…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 h-8 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
          />
          <span className="text-sm text-muted-foreground whitespace-nowrap">
            {filtered.length} item{filtered.length !== 1 ? "s" : ""}
          </span>
        </div>
        
        {selectedIds.size > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground mr-2">{selectedIds.size} selected</span>
            <Button
              size="sm"
              variant="destructive"
              disabled={isMutating || !hasWorkspace}
              title={!hasWorkspace ? "Continue as guest to review" : undefined}
              onClick={() => batchRejectMutation.mutate(Array.from(selectedIds))}
            >
              Batch Reject
            </Button>
            <Button
              size="sm"
              disabled={isMutating || !hasWorkspace}
              title={!hasWorkspace ? "Continue as guest to review" : undefined}
              onClick={() => batchApproveMutation.mutate(Array.from(selectedIds))}
            >
              Batch Approve
            </Button>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 px-4 py-1 text-sm text-muted-foreground">
        <input
          type="checkbox"
          className="w-4 h-4 rounded border-gray-300"
          checked={selectedIds.size > 0 && selectedIds.size === filtered.length}
          ref={el => { if (el) el.indeterminate = selectedIds.size > 0 && selectedIds.size < filtered.length; }}
          onChange={toggleAll}
          disabled={!hasWorkspace}
        />
        <span>Select All</span>
      </div>

      {hasWorkspace && isLoading && (
        <div className="space-y-2">
          {[1, 2, 3].map((n) => (
            <div key={n} className="h-16 rounded-lg border bg-muted/20 animate-pulse" />
          ))}
        </div>
      )}

      {hasWorkspace && isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          Failed to load review queue.{" "}
          <button className="underline" onClick={() => refetch()}>
            Retry
          </button>
        </div>
      )}

      {(!hasWorkspace || (!isLoading && !isError)) && filtered.length === 0 && (
        <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground text-sm">
          {search ? "No results match your search." : "No invoices need review."}
        </div>
      )}

      <div className="space-y-2">
        {filtered.map((item) => (
          <QueueRow
            key={item.id}
            item={item}
            isSelected={selectedIds.has(item.id)}
            onToggleSelect={() => toggleSelect(item.id)}
            isDemo={!hasWorkspace}
          />
        ))}
      </div>
    </div>
  );
}
