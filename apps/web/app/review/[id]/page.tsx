"use client";

import { use } from "react";
import dynamic from "next/dynamic";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, XCircle, ArrowLeft, AlertTriangle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { FieldEditor } from "@/components/FieldEditor";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";

const PdfViewer = dynamic(() => import("@/components/PdfViewer").then((m) => m.PdfViewer), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-64 text-muted-foreground text-sm rounded-lg border">
      Loading PDF viewer…
    </div>
  ),
});

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function ReviewDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: invoice, isLoading, isError } = useQuery({
    queryKey: ["invoice", id],
    queryFn: () => apiClient.invoices.get(id),
  });

  const approveMutation = useMutation({
    mutationFn: () => apiClient.review.approve(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      router.push("/review");
    },
  });

  const rejectMutation = useMutation({
    mutationFn: () => apiClient.review.reject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      router.push("/review");
    },
  });

  async function handleFieldSave(fieldId: string, value: string | null) {
    await apiClient.review.updateField(id, fieldId, value);
    queryClient.invalidateQueries({ queryKey: ["invoice", id] });
  }

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto space-y-4">
        <div className="h-8 w-48 rounded bg-muted animate-pulse" />
        <div className="h-[600px] rounded-lg border bg-muted/20 animate-pulse" />
      </div>
    );
  }

  if (isError || !invoice) {
    return (
      <div className="max-w-7xl mx-auto space-y-4">
        <Link href="/review" className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "gap-1")}>
          <ArrowLeft className="h-4 w-4" /> Review Queue
        </Link>
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          Invoice not found.
        </div>
      </div>
    );
  }

  const pdfUrl = `${API_BASE}/documents/${invoice.document_id}/file`;
  const isMutating = approveMutation.isPending || rejectMutation.isPending;

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <Link
            href="/review"
            className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "gap-1")}
          >
            <ArrowLeft className="h-4 w-4" /> Back
          </Link>
          <div>
            <h1 className="text-xl font-semibold truncate max-w-sm">{invoice.filename}</h1>
            <p className="text-sm text-muted-foreground">
              {invoice.vendor_name ?? "Unknown vendor"}
              {invoice.invoice_date ? ` · ${invoice.invoice_date}` : ""}
            </p>
          </div>
        </div>

        {invoice.needs_review && (
          <div className="flex items-center gap-2">
            <Button
              variant="destructive"
              size="sm"
              onClick={() => rejectMutation.mutate()}
              disabled={isMutating}
              className="gap-1"
            >
              <XCircle className="h-4 w-4" />
              Reject
            </Button>
            <Button
              size="sm"
              onClick={() => approveMutation.mutate()}
              disabled={isMutating}
              className="gap-1"
            >
              <CheckCircle2 className="h-4 w-4" />
              Approve
            </Button>
          </div>
        )}
      </div>

      {invoice.review_reasons.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800 dark:border-yellow-900 dark:bg-yellow-950/30 dark:text-yellow-300">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          <div className="space-y-0.5">
            <p className="font-medium">Needs review</p>
            <ul className="list-disc list-inside space-y-0.5">
              {invoice.review_reasons.map((r) => (
                <li key={r} className="text-xs">{r}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Two-column layout */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* PDF */}
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">Document</h2>
          <PdfViewer url={pdfUrl} />
        </div>

        {/* Fields */}
        <div className="space-y-4">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
            Extracted Fields
          </h2>

          {/* Summary strip */}
          <div className="grid grid-cols-2 gap-3 text-sm">
            {[
              ["Invoice #", invoice.invoice_number],
              ["Date", invoice.invoice_date],
              ["Due Date", invoice.due_date],
              ["Vendor", invoice.vendor_name],
              ["Buyer", invoice.buyer_name],
              ["Total", invoice.total_amount ? `${invoice.currency ?? ""} ${invoice.total_amount}` : null],
            ].map(([label, value]) => (
              <div key={label} className="space-y-0.5">
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="font-medium truncate">{value ?? "—"}</p>
              </div>
            ))}
          </div>

          {/* Per-field editors */}
          {invoice.fields.length > 0 && (
            <div className="space-y-0.5 rounded-lg border divide-y">
              {invoice.fields.map((field) => (
                <FieldEditor key={field.id} field={field} onSave={handleFieldSave} />
              ))}
            </div>
          )}

          {/* Line items */}
          {invoice.line_items.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Line Items
              </h3>
              <div className="rounded-lg border text-sm overflow-auto">
                <table className="w-full text-left">
                  <thead className="border-b bg-muted/30">
                    <tr>
                      <th className="px-3 py-2 font-medium text-muted-foreground text-xs">Description</th>
                      <th className="px-3 py-2 font-medium text-muted-foreground text-xs w-16">Qty</th>
                      <th className="px-3 py-2 font-medium text-muted-foreground text-xs w-24">Unit Price</th>
                      <th className="px-3 py-2 font-medium text-muted-foreground text-xs w-24">Total</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {invoice.line_items.map((li) => (
                      <tr key={li.id}>
                        <td className="px-3 py-2">{li.description ?? "—"}</td>
                        <td className="px-3 py-2 tabular-nums">{li.quantity ?? "—"}</td>
                        <td className="px-3 py-2 tabular-nums">{li.unit_price ?? "—"}</td>
                        <td className="px-3 py-2 tabular-nums">{li.total ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
