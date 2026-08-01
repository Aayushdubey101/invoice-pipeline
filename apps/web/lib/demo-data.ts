import type { ReviewQueue, ReviewQueueItem, Vendor, VendorList } from "@/lib/types";
import type { DashboardStats, BatchSummary } from "@/lib/api-client";

const VENDOR_NAMES = [
  "Acme Supplies Co.",
  "Global Freight Logistics",
  "Nimbus Cloud Services",
  "Bluepeak Office Solutions",
  "Ferrotech Manufacturing",
  "Sunrise Catering Group",
  "Vertex Consulting Partners",
  "Northwind Traders",
  "Apex Hardware Ltd.",
  "Coastal Print & Media",
];
const CURRENCIES = ["USD", "EUR", "GBP", "INR"];
const REVIEW_REASONS = [
  "low_confidence_total",
  "vendor_unmatched",
  "date_ambiguous",
  "math_mismatch",
  "missing_tax_id",
];
const DOC_STATUSES = ["needs_review", "processing", "complete", "pending"] as const;

function pick<T>(arr: readonly T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}
function randInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}
function randId(prefix: string): string {
  return `${prefix}_demo_${Math.random().toString(36).slice(2, 10)}`;
}
function daysAgo(n: number): string {
  return new Date(Date.now() - n * 86_400_000).toISOString();
}

export function generateDemoReviewQueue(): ReviewQueue {
  const items: ReviewQueueItem[] = Array.from({ length: randInt(4, 9) }, () => {
    const status = pick(DOC_STATUSES);
    return {
      id: randId("inv"),
      document_id: randId("doc"),
      invoice_number: `INV-${randInt(1000, 9999)}`,
      invoice_date: daysAgo(randInt(0, 30)).slice(0, 10),
      vendor_id: randId("ven"),
      vendor_name: pick(VENDOR_NAMES),
      buyer_name: "Demo Workspace Inc.",
      total_amount: (randInt(50, 5000) + Math.random()).toFixed(2),
      currency: pick(CURRENCIES),
      needs_review: status === "needs_review",
      review_reasons: status === "needs_review" ? [pick(REVIEW_REASONS), pick(REVIEW_REASONS)] : [],
      document_status: status,
      filename: `invoice_${randInt(100, 999)}.pdf`,
      created_at: daysAgo(randInt(0, 14)),
    };
  });
  return { items, total: items.length };
}

export function generateDemoBatches(): { batches: BatchSummary[]; total: number } {
  const batches: BatchSummary[] = Array.from({ length: randInt(3, 6) }, () => {
    const total = randInt(3, 20);
    const failed = randInt(0, Math.min(2, total));
    const completed = Math.max(total - failed - randInt(0, 1), 0);
    return {
      batch_id: randId("batch"),
      upload_source: pick(["web", "email", "folder"]),
      total_files: total,
      completed,
      failed,
      pending: Math.max(total - completed - failed, 0),
      skipped: 0,
      avg_confidence: Math.random() * 0.3 + 0.7,
      processing_time_ms: randInt(800, 12_000),
      created_at: daysAgo(randInt(0, 20)),
    };
  });
  return { batches, total: batches.length };
}

export function generateDemoDashboardStats(): DashboardStats {
  const invoices = randInt(40, 300);
  const needsReview = randInt(2, 20);
  const failed = randInt(0, 8);
  const processing = randInt(0, 5);
  return {
    totals: {
      invoices,
      needs_review: needsReview,
      approved: Math.max(invoices - needsReview - failed, 0),
      failed_documents: failed,
      processing_documents: processing,
      complete_documents: Math.max(invoices - failed - processing, 0),
      batches: randInt(5, 25),
    },
    recent_uploads: Array.from({ length: randInt(3, 6) }, () => ({
      document_id: randId("doc"),
      filename: `invoice_${randInt(100, 999)}.pdf`,
      status: pick(["complete", "processing", "needs_review", "failed"]),
      batch_id: randId("batch"),
      created_at: daysAgo(randInt(0, 5)),
    })),
    vendor_statistics: VENDOR_NAMES.slice(0, 6)
      .map((vendor_name) => ({ vendor_name, invoice_count: randInt(2, 40) }))
      .sort((a, b) => b.invoice_count - a.invoice_count),
  };
}

export function generateDemoVendors(): VendorList {
  const items: Vendor[] = VENDOR_NAMES.map((name) => ({
    id: randId("ven"),
    canonical_name: name,
    aliases: [],
    address: null,
    tax_id: null,
    status: pick(["active", "active", "active", "pending_review"] as const),
    created_at: daysAgo(randInt(10, 200)),
    tax_ids: [],
    historical_invoice_numbers: [],
    preferred_currency: pick(CURRENCIES),
    preferred_payment_terms: pick(["Net 30", "Net 15", "Due on receipt"]),
    frequently_used_products: [],
    avg_confidence: Math.random() * 0.2 + 0.8,
    invoice_count: randInt(1, 40),
    layout_patterns: {},
  }));
  return { items, total: items.length };
}
