"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Clock, XCircle, ChevronRight } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import type { ReviewQueueItem } from "@/lib/types";

const STATUS_ICON: Record<string, React.ReactNode> = {
  complete: <CheckCircle2 className="h-4 w-4 text-green-500" />,
  failed: <XCircle className="h-4 w-4 text-red-500" />,
  needs_review: <AlertTriangle className="h-4 w-4 text-yellow-500" />,
  pending: <Clock className="h-4 w-4 text-muted-foreground" />,
  processing: <Clock className="h-4 w-4 text-blue-500 animate-spin" />,
};

function QueueRow({ item }: { item: ReviewQueueItem }) {
  return (
    <Link
      href={`/review/${item.id}`}
      className="flex items-center gap-4 px-4 py-3 rounded-lg border bg-card hover:bg-muted/40 transition-colors group"
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
  );
}

export function ReviewQueue() {
  const [search, setSearch] = useState("");

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["review-queue"],
    queryFn: () => apiClient.review.queue(),
  });

  const items = data?.items ?? [];
  const filtered = search
    ? items.filter(
        (i) =>
          i.filename.toLowerCase().includes(search.toLowerCase()) ||
          i.vendor_name?.toLowerCase().includes(search.toLowerCase()) ||
          i.invoice_number?.toLowerCase().includes(search.toLowerCase())
      )
    : items;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
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

      {isLoading && (
        <div className="space-y-2">
          {[1, 2, 3].map((n) => (
            <div key={n} className="h-16 rounded-lg border bg-muted/20 animate-pulse" />
          ))}
        </div>
      )}

      {isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          Failed to load review queue.{" "}
          <button className="underline" onClick={() => refetch()}>
            Retry
          </button>
        </div>
      )}

      {!isLoading && !isError && filtered.length === 0 && (
        <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground text-sm">
          {search ? "No results match your search." : "No invoices need review."}
        </div>
      )}

      <div className="space-y-2">
        {filtered.map((item) => (
          <QueueRow key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}
