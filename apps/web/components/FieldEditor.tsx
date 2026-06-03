"use client";

import { useState, useRef } from "react";
import { Check, X, Pencil } from "lucide-react";
import { cn } from "@/lib/utils";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import type { InvoiceField } from "@/lib/types";

interface FieldEditorProps {
  field: InvoiceField;
  onSave: (fieldId: string, value: string | null) => Promise<void>;
}

export function FieldEditor({ field, onSave }: FieldEditorProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(
    field.reviewed_value ?? field.canonical_value ?? field.raw_value ?? ""
  );
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const displayValue = field.reviewed_value ?? field.canonical_value ?? field.raw_value;

  async function handleSave() {
    setSaving(true);
    try {
      await onSave(field.id, draft || null);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  function handleCancel() {
    setDraft(field.reviewed_value ?? field.canonical_value ?? field.raw_value ?? "");
    setEditing(false);
  }

  return (
    <div
      className={cn(
        "group flex items-start gap-2 rounded-md px-2 py-1.5 transition-colors",
        field.needs_review && !field.reviewed && "bg-yellow-50 dark:bg-yellow-950/20"
      )}
    >
      <div className="flex-1 min-w-0 space-y-0.5">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground font-medium capitalize">
            {field.field_name.replace(/_/g, " ")}
          </span>
          <ConfidenceBadge confidence={field.confidence} />
          {field.reviewed && (
            <span className="text-[10px] text-green-600 dark:text-green-400 font-medium">
              ✓ reviewed
            </span>
          )}
        </div>

        {editing ? (
          <div className="flex items-center gap-1">
            <input
              ref={inputRef}
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSave();
                if (e.key === "Escape") handleCancel();
              }}
              disabled={saving}
              className="flex-1 h-7 rounded border border-input bg-background px-2 text-sm outline-none focus:ring-2 focus:ring-ring/50"
            />
            <button
              onClick={handleSave}
              disabled={saving}
              className="h-7 w-7 flex items-center justify-center rounded border border-green-300 bg-green-50 text-green-700 hover:bg-green-100 disabled:opacity-50 dark:border-green-800 dark:bg-green-950 dark:text-green-300"
              aria-label="Save"
            >
              <Check className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={handleCancel}
              disabled={saving}
              className="h-7 w-7 flex items-center justify-center rounded border border-border bg-background text-muted-foreground hover:bg-muted disabled:opacity-50"
              aria-label="Cancel"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-1.5">
            <span
              className={cn(
                "text-sm break-all",
                !displayValue && "text-muted-foreground italic"
              )}
            >
              {displayValue ?? "—"}
            </span>
            <button
              onClick={() => setEditing(true)}
              className="invisible group-hover:visible shrink-0 h-5 w-5 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-muted"
              aria-label={`Edit ${field.field_name}`}
            >
              <Pencil className="h-3 w-3" />
            </button>
          </div>
        )}

        {field.evidence && !editing && (
          <p className="text-[11px] text-muted-foreground bg-muted/40 rounded px-1.5 py-0.5 mt-1 italic line-clamp-2">
            "{field.evidence}"
          </p>
        )}
      </div>
    </div>
  );
}
