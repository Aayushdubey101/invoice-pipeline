"use client";

import { use, useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, XCircle, ArrowLeft, AlertTriangle, Undo2, ChevronDown, ChevronUp, Keyboard } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { FieldEditor } from "@/components/FieldEditor";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
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

  const [activeFieldId, setActiveFieldId] = useState<string | null>(null);
  const [undoStack, setUndoStack] = useState<{fieldId: string, prevValue: string | null}[]>([]);

  const handleFieldSave = useCallback(async (fieldId: string, value: string | null) => {
    if (!invoice) return;
    const field = invoice.fields.find(f => f.id === fieldId);
    if (field) {
      setUndoStack(prev => [...prev, { fieldId, prevValue: field.canonical_value }]);
    }
    await apiClient.review.updateField(id, fieldId, value);
    queryClient.invalidateQueries({ queryKey: ["invoice", id] });
  }, [id, invoice, queryClient]);

  const handleUndo = useCallback(async () => {
    const lastAction = undoStack[undoStack.length - 1];
    if (!lastAction) return;
    
    setUndoStack(prev => prev.slice(0, -1));
    await apiClient.review.updateField(id, lastAction.fieldId, lastAction.prevValue);
    queryClient.invalidateQueries({ queryKey: ["invoice", id] });
  }, [id, undoStack, queryClient]);

  const navigateFields = useCallback((direction: 'next' | 'prev', onlyNeedsReview = false) => {
    if (!invoice?.fields.length) return;
    const fields = invoice.fields;
    
    let currentIndex = fields.findIndex(f => f.id === activeFieldId);
    if (currentIndex === -1) currentIndex = direction === 'next' ? -1 : fields.length;

    let nextIndex = currentIndex;
    let found = false;
    for (let i = 0; i < fields.length; i++) {
      nextIndex = direction === 'next' 
        ? (nextIndex + 1) % fields.length
        : (nextIndex - 1 + fields.length) % fields.length;
      
      if (!onlyNeedsReview || fields[nextIndex].needs_review) {
        found = true;
        break;
      }
    }

    if (found) {
      setActiveFieldId(fields[nextIndex].id);
    }
  }, [invoice, activeFieldId]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger shortcuts if user is typing in an input unless it's with Alt modifier
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        if (!e.altKey) return;
      }
      
      if (e.altKey && e.key === 'ArrowDown') {
        e.preventDefault();
        navigateFields('next', false);
      } else if (e.altKey && e.key === 'ArrowUp') {
        e.preventDefault();
        navigateFields('prev', false);
      } else if (e.altKey && e.key === 'n') {
        e.preventDefault();
        navigateFields('next', true); // Next issue
      } else if (e.altKey && e.key === 'z') {
        e.preventDefault();
        handleUndo();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [navigateFields, handleUndo]);

  // <img>/<Document> can't send our X-Workspace-Id/Authorization headers, so
  // /file 401s when linked to directly — fetch it ourselves into a blob: URL.
  const [docBlobUrl, setDocBlobUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!invoice?.document_id) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    apiClient.documents.fileBlobUrl(invoice.document_id).then((url) => {
      if (cancelled) {
        URL.revokeObjectURL(url);
        return;
      }
      objectUrl = url;
      setDocBlobUrl(url);
    });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [invoice?.document_id]);

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

  const isImage = /\.(png|jpe?g|gif|webp|bmp|tiff?)$/i.test(invoice.filename);
  
  const activeField = invoice.fields.find(f => f.id === activeFieldId);
  const activePage = activeField?.page != null ? activeField.page + 1 : null;
  const activeBbox = activeField?.bbox ?? null;
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
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-semibold truncate max-w-sm">{invoice.filename}</h1>
              {invoice.confidence_breakdown && (
                <ConfidenceBadge
                  confidence={invoice.confidence_breakdown.overall}
                  breakdown={invoice.confidence_breakdown}
                />
              )}
            </div>
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

      {/* Toolbar / Shortcuts */}
      <div className="flex items-center justify-between bg-muted/30 border rounded-lg p-2 text-sm">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => navigateFields('prev')} className="gap-1 text-xs h-7">
            <ChevronUp className="h-3 w-3" /> Prev Field <kbd className="ml-1 bg-muted px-1 rounded text-[10px]">Alt+↑</kbd>
          </Button>
          <Button variant="outline" size="sm" onClick={() => navigateFields('next')} className="gap-1 text-xs h-7">
            <ChevronDown className="h-3 w-3" /> Next Field <kbd className="ml-1 bg-muted px-1 rounded text-[10px]">Alt+↓</kbd>
          </Button>
          <Button variant="outline" size="sm" onClick={() => navigateFields('next', true)} className="gap-1 text-xs h-7 border-yellow-200 bg-yellow-50/50 hover:bg-yellow-100 dark:border-yellow-900/50 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-300">
            <AlertTriangle className="h-3 w-3" /> Next Issue <kbd className="ml-1 bg-yellow-100 dark:bg-yellow-900 px-1 rounded text-[10px]">Alt+N</kbd>
          </Button>
        </div>
        <div className="flex items-center gap-2">
          {undoStack.length > 0 && (
            <Button variant="ghost" size="sm" onClick={handleUndo} className="gap-1 text-xs h-7 text-muted-foreground">
              <Undo2 className="h-3 w-3" /> Undo <kbd className="ml-1 bg-muted px-1 rounded text-[10px]">Alt+Z</kbd>
            </Button>
          )}
          <div className="text-muted-foreground text-xs flex items-center gap-1">
            <Keyboard className="h-3 w-3" /> Shortcuts enabled
          </div>
        </div>
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
          {docBlobUrl ? (
            <PdfViewer
              url={docBlobUrl}
              isImage={isImage}
              highlightPage={activePage}
              highlightBbox={activeBbox}
            />
          ) : (
            <div className="flex items-center justify-center h-64 text-muted-foreground text-sm rounded-lg border">
              Loading document…
            </div>
          )}
        </div>

        {/* Fields */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
              Extracted Fields
            </h2>
            {invoice.confidence_breakdown && (
              <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                Quality: {(invoice.confidence_breakdown.overall * 100).toFixed(0)}%
              </span>
            )}
          </div>

          {invoice.confidence_breakdown && (
            <div className="flex flex-wrap gap-1.5 text-xs">
              {Object.entries(invoice.confidence_breakdown)
                .filter(([key]) => key !== "overall")
                .map(([key, value]) => (
                  <span
                    key={key}
                    className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-muted-foreground capitalize"
                  >
                    {key} <span className="font-medium text-foreground">{Math.round(value * 100)}%</span>
                  </span>
                ))}
            </div>
          )}

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
                <FieldEditor
                  key={field.id}
                  field={field}
                  isEditing={activeFieldId === field.id}
                  onEdit={(editing) => {
                    if (editing) setActiveFieldId(field.id);
                    else if (activeFieldId === field.id) setActiveFieldId(null);
                  }}
                  onSave={handleFieldSave} 
                />
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
                      <th className="px-3 py-2 font-medium text-muted-foreground text-xs">Type</th>
                      <th className="px-3 py-2 font-medium text-muted-foreground text-xs">Description</th>
                      <th className="px-3 py-2 font-medium text-muted-foreground text-xs w-16">Qty</th>
                      <th className="px-3 py-2 font-medium text-muted-foreground text-xs w-24">Unit Price</th>
                      <th className="px-3 py-2 font-medium text-muted-foreground text-xs w-24">Total</th>
                      <th className="px-3 py-2 font-medium text-muted-foreground text-xs w-10 text-center" title="Math valid: qty × unit_price ≈ total">✓</th>
                      <th className="px-3 py-2 font-medium text-muted-foreground text-xs w-10">Pg</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {invoice.line_items.map((li) => {
                      const isNonItem = li.row_type && !["item", "unknown"].includes(li.row_type);
                      const rowBg = isNonItem ? "bg-muted/20" : "";
                      const mathIcon =
                        li.math_valid === true ? (
                          <span className="text-green-600 font-bold" title="Math check passed">✓</span>
                        ) : li.math_valid === false ? (
                          <span className="text-red-500 font-bold" title="Math mismatch: qty × price ≠ total">✗</span>
                        ) : (
                          <span className="text-muted-foreground text-xs" title="Insufficient data">—</span>
                        );

                      const rowTypeBadge = li.row_type && li.row_type !== "item" ? (
                        <span className={cn(
                          "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide",
                          {
                            "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300": li.row_type === "subtotal",
                            "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300": li.row_type === "tax",
                            "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300": li.row_type === "discount",
                            "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300": li.row_type === "total",
                            "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300": li.row_type === "shipping",
                            "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400": !["subtotal","tax","discount","total","shipping"].includes(li.row_type ?? ""),
                          }
                        )}>
                          {li.row_type}
                        </span>
                      ) : null;

                      const cellStyle = (conf?: number) =>
                        conf !== undefined && conf < 0.75
                          ? "text-yellow-700 dark:text-yellow-400"
                          : "";

                      return (
                        <tr key={li.id} className={cn("hover:bg-muted/10", rowBg)}>
                          <td className="px-3 py-2">
                            {rowTypeBadge ?? <span className="text-muted-foreground text-xs">item</span>}
                          </td>
                          <td className={cn("px-3 py-2", cellStyle(li.description_confidence))}>
                            {li.description ?? "—"}
                          </td>
                          <td className={cn("px-3 py-2 tabular-nums", cellStyle(li.quantity_confidence))}>
                            {li.quantity ?? "—"}
                          </td>
                          <td className={cn("px-3 py-2 tabular-nums", cellStyle(li.unit_price_confidence))}>
                            {li.unit_price ?? "—"}
                          </td>
                          <td className={cn("px-3 py-2 tabular-nums", cellStyle(li.total_confidence))}>
                            {li.total ?? "—"}
                          </td>
                          <td className="px-3 py-2 text-center">{mathIcon}</td>
                          <td className="px-3 py-2 text-muted-foreground text-xs">
                            {li.page !== null && li.page !== undefined ? li.page + 1 : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {/* Math error summary */}
              {invoice.line_items.some((li) => li.math_valid === false) && (
                <p className="text-xs text-red-600 dark:text-red-400">
                  ⚠ Some rows have quantity × unit price ≠ total. Please verify before approving.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
