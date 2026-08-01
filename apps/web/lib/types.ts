import { z } from "zod";

// ── Confidence Breakdown ───────────────────────────────────────────────────────
// Shape produced by confidence/engine.py::ConfidenceEngine.model_dump_summary():
// a flat map of named signal scores plus "overall". See CLAUDE.md "Confidence Scoring".

export const ConfidenceBreakdownSchema = z.object({ overall: z.number() }).catchall(z.number());

// ── Schemas ───────────────────────────────────────────────────────────────────

export const FieldValueSchema = z.object({
  value: z.string().nullable(),
  confidence: z.number(),
  evidence: z.string().nullable(),
});

export const LineItemSchema = z.object({
  description: FieldValueSchema,
  quantity: FieldValueSchema,
  unit_price: FieldValueSchema,
  total: FieldValueSchema,
});

export const RawInvoiceSchema = z.object({
  invoice_number: FieldValueSchema,
  invoice_date: FieldValueSchema,
  due_date: FieldValueSchema,
  vendor_name: FieldValueSchema,
  vendor_address: FieldValueSchema,
  vendor_tax_id: FieldValueSchema,
  buyer_name: FieldValueSchema,
  buyer_address: FieldValueSchema,
  subtotal: FieldValueSchema,
  tax_amount: FieldValueSchema,
  total_amount: FieldValueSchema,
  currency: FieldValueSchema,
  payment_terms: FieldValueSchema,
  purchase_order: FieldValueSchema,
  line_items: z.array(LineItemSchema),
});

export const InvoiceFieldSchema = z.object({
  id: z.string(),
  field_name: z.string(),
  raw_value: z.string().nullable(),
  canonical_value: z.string().nullable(),
  confidence: z.number(),
  evidence: z.string().nullable(),
  page: z.number().nullable(),
  bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]).nullable(),
  needs_review: z.boolean(),
  reviewed: z.boolean(),
  reviewed_value: z.string().nullable(),
});

export const LineItemRowSchema = z.object({
  id: z.string(),
  position: z.number(),
  description: z.string().nullable(),
  quantity: z.string().nullable(),
  unit_price: z.string().nullable(),
  total: z.string().nullable(),
  // Phase 4 rich fields
  description_confidence: z.number().optional().default(0),
  quantity_confidence: z.number().optional().default(0),
  unit_price_confidence: z.number().optional().default(0),
  total_confidence: z.number().optional().default(0),
  row_type: z.string().optional().default("item"),
  math_valid: z.boolean().nullable().optional(),
  page: z.number().nullable().optional(),
  bbox: z.array(z.number()).nullable().optional(),
  source_evidence: z.string().nullable().optional(),
  table_index: z.number().optional().default(0),
});

export const InvoiceDetailSchema = z.object({
  id: z.string(),
  document_id: z.string(),
  invoice_number: z.string().nullable(),
  invoice_date: z.string().nullable(),
  due_date: z.string().nullable(),
  vendor_id: z.string().nullable(),
  vendor_name: z.string().nullable(),
  buyer_name: z.string().nullable(),
  subtotal: z.string().nullable(),
  tax_amount: z.string().nullable(),
  total_amount: z.string().nullable(),
  currency: z.string().nullable(),
  payment_terms: z.string().nullable(),
  purchase_order: z.string().nullable(),
  needs_review: z.boolean(),
  review_reasons: z.array(z.string()),
  filename: z.string(),
  document_status: z.string(),
  fields: z.array(InvoiceFieldSchema),
  line_items: z.array(LineItemRowSchema),
  raw_extraction: z.record(z.string(), z.unknown()),
  confidence_breakdown: ConfidenceBreakdownSchema.nullable().optional(),
});

export const ReviewQueueItemSchema = z.object({
  id: z.string(),
  document_id: z.string(),
  invoice_number: z.string().nullable(),
  invoice_date: z.string().nullable(),
  vendor_id: z.string().nullable(),
  vendor_name: z.string().nullable(),
  buyer_name: z.string().nullable(),
  total_amount: z.string().nullable(),
  currency: z.string().nullable(),
  needs_review: z.boolean(),
  review_reasons: z.array(z.string()),
  document_status: z.string(),
  filename: z.string(),
  created_at: z.string(),
});

export const ReviewQueueSchema = z.object({
  items: z.array(ReviewQueueItemSchema),
  total: z.number(),
});

export const VendorSchema = z.object({
  id: z.string(),
  canonical_name: z.string(),
  aliases: z.array(z.string()),
  address: z.string().nullable().optional(),
  tax_id: z.string().nullable().optional(),
  status: z.enum(["active", "pending_review", "inactive"]),
  created_at: z.string().optional(),
  // Phase 5: Vendor Intelligence Memory
  tax_ids: z.array(z.string()).optional().default([]),
  historical_invoice_numbers: z.array(z.string()).optional().default([]),
  preferred_currency: z.string().nullable().optional(),
  preferred_payment_terms: z.string().nullable().optional(),
  frequently_used_products: z.array(z.string()).optional().default([]),
  avg_confidence: z.number().nullable().optional(),
  invoice_count: z.number().optional().default(0),
  layout_patterns: z.record(z.string(), z.unknown()).optional().default({}),
});

export const VendorListSchema = z.object({
  items: z.array(VendorSchema),
  total: z.number(),
});

export const UploadResponseSchema = z.object({
  document_id: z.string(),
  status: z.string(),
  errors: z.array(z.record(z.string(), z.unknown())),
});

// ── Inferred types ────────────────────────────────────────────────────────────

export type FieldValue = z.infer<typeof FieldValueSchema>;
export type ConfidenceBreakdown = z.infer<typeof ConfidenceBreakdownSchema>;
export type LineItem = z.infer<typeof LineItemSchema>;
export type RawInvoice = z.infer<typeof RawInvoiceSchema>;
export type InvoiceField = z.infer<typeof InvoiceFieldSchema>;
export type LineItemRow = z.infer<typeof LineItemRowSchema>;
export type InvoiceDetail = z.infer<typeof InvoiceDetailSchema>;
export type ReviewQueueItem = z.infer<typeof ReviewQueueItemSchema>;
export type ReviewQueue = z.infer<typeof ReviewQueueSchema>;
export type Vendor = z.infer<typeof VendorSchema>;
export type VendorList = z.infer<typeof VendorListSchema>;
export type UploadResponse = z.infer<typeof UploadResponseSchema>;

export type DocumentStatus = "pending" | "processing" | "complete" | "failed" | "needs_review";
export type DocumentType = "text_pdf" | "scanned_pdf" | "image" | "email" | "unknown";
export type VendorStatus = "active" | "pending_review" | "inactive";
