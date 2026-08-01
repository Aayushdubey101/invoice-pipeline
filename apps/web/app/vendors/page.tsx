"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { Pencil, Check, X, Building2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api-client";
import type { Vendor } from "@/lib/types";
import { WorkspaceGuardDialog } from "@/components/WorkspaceGuardDialog";
import { useWorkspaceSession } from "@/contexts/WorkspaceSessionContext";
import { generateDemoVendors } from "@/lib/demo-data";

const STATUS_BADGE: Record<string, string> = {
  active: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  pending_review: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300",
  inactive: "bg-muted text-muted-foreground",
};

interface EditState {
  canonical_name: string;
  aliases: string;
}

function ConfidencePip({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    value >= 0.85
      ? "bg-green-500"
      : value >= 0.65
      ? "bg-yellow-400"
      : "bg-red-500";
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1.5 w-20 rounded-full bg-muted overflow-hidden">
        <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums text-muted-foreground">{pct}%</span>
    </div>
  );
}

function VendorRow({ vendor, readOnly = false }: { vendor: Vendor; readOnly?: boolean }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [showMemory, setShowMemory] = useState(false);
  const [draft, setDraft] = useState<EditState>({
    canonical_name: vendor.canonical_name,
    aliases: vendor.aliases.join(", "),
  });

  const mutation = useMutation({
    mutationFn: (data: EditState) =>
      apiClient.vendors.update(vendor.id, {
        canonical_name: data.canonical_name.trim(),
        aliases: data.aliases
          .split(",")
          .map((a) => a.trim())
          .filter(Boolean),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendors"] });
      setEditing(false);
    },
  });

  function handleCancel() {
    setDraft({ canonical_name: vendor.canonical_name, aliases: vendor.aliases.join(", ") });
    setEditing(false);
  }

  const hasMemory = (vendor.invoice_count ?? 0) > 0;

  return (
    <div className="rounded-lg border bg-card group">
      <div className="flex items-start gap-3 px-4 py-3">
        <Building2 className="h-5 w-5 text-muted-foreground mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0 space-y-1">
          {editing ? (
            <div className="space-y-2">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Canonical name</label>
                <input
                  autoFocus
                  value={draft.canonical_name}
                  onChange={(e) => setDraft((d) => ({ ...d, canonical_name: e.target.value }))}
                  className="w-full h-7 rounded border border-input bg-background px-2 text-sm outline-none focus:ring-2 focus:ring-ring/50"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Aliases (comma-separated)</label>
                <input
                  value={draft.aliases}
                  onChange={(e) => setDraft((d) => ({ ...d, aliases: e.target.value }))}
                  className="w-full h-7 rounded border border-input bg-background px-2 text-sm outline-none focus:ring-2 focus:ring-ring/50"
                />
              </div>
              <div className="flex gap-2 pt-1">
                <Button
                  size="sm"
                  onClick={() => mutation.mutate(draft)}
                  disabled={mutation.isPending}
                  className="gap-1"
                >
                  <Check className="h-3.5 w-3.5" />
                  Save
                </Button>
                <Button size="sm" variant="outline" onClick={handleCancel} disabled={mutation.isPending}>
                  <X className="h-3.5 w-3.5" />
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-sm">{vendor.canonical_name}</span>
                <span
                  className={cn(
                    "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium",
                    STATUS_BADGE[vendor.status] ?? STATUS_BADGE.inactive
                  )}
                >
                  {vendor.status.replace("_", " ")}
                </span>
                {vendor.preferred_currency && (
                  <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
                    {vendor.preferred_currency}
                  </span>
                )}
                {hasMemory && (
                  <span className="text-[10px] text-muted-foreground">
                    {vendor.invoice_count} invoice{vendor.invoice_count !== 1 ? "s" : ""}
                  </span>
                )}
              </div>
              {vendor.aliases.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  Also known as: {vendor.aliases.join(", ")}
                </p>
              )}
              {hasMemory && vendor.avg_confidence != null && (
                <ConfidencePip value={vendor.avg_confidence} />
              )}
            </>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {hasMemory && !editing && (
            <button
              onClick={() => setShowMemory((v) => !v)}
              className={cn(
                "h-7 w-7 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-muted text-xs",
                showMemory && "bg-muted text-foreground"
              )}
              aria-label="Toggle vendor intelligence"
              title="Vendor intelligence"
            >
              🧠
            </button>
          )}
          {!editing && !readOnly && (
            <button
              onClick={() => setEditing(true)}
              className="invisible group-hover:visible h-7 w-7 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-muted shrink-0"
              aria-label={`Edit ${vendor.canonical_name}`}
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Phase 5: Intelligence memory panel */}
      {showMemory && hasMemory && (
        <div className="border-t px-4 py-3 bg-muted/20 space-y-3 text-xs">
          <p className="font-medium text-muted-foreground uppercase tracking-wide text-[10px]">
            Vendor Intelligence
          </p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-2">
            {vendor.preferred_currency && (
              <div>
                <span className="text-muted-foreground">Preferred currency</span>
                <p className="font-medium">{vendor.preferred_currency}</p>
              </div>
            )}
            {vendor.preferred_payment_terms && (
              <div>
                <span className="text-muted-foreground">Preferred terms</span>
                <p className="font-medium">{vendor.preferred_payment_terms}</p>
              </div>
            )}
            {vendor.tax_ids && vendor.tax_ids.length > 0 && (
              <div>
                <span className="text-muted-foreground">Known tax IDs</span>
                <p className="font-medium">{vendor.tax_ids.join(", ")}</p>
              </div>
            )}
            <div>
              <span className="text-muted-foreground">Avg extraction quality</span>
              {vendor.avg_confidence != null ? (
                <ConfidencePip value={vendor.avg_confidence} />
              ) : (
                <p className="font-medium">—</p>
              )}
            </div>
          </div>
          {vendor.frequently_used_products && vendor.frequently_used_products.length > 0 && (
            <div>
              <span className="text-muted-foreground">Frequent products</span>
              <div className="mt-1 flex flex-wrap gap-1">
                {vendor.frequently_used_products.slice(0, 8).map((p) => (
                  <span
                    key={p}
                    className="inline-flex items-center rounded px-1.5 py-0.5 bg-muted text-muted-foreground font-mono text-[10px]"
                  >
                    {p.length > 40 ? p.slice(0, 40) + "…" : p}
                  </span>
                ))}
              </div>
            </div>
          )}
          {vendor.historical_invoice_numbers && vendor.historical_invoice_numbers.length > 0 && (
            <div>
              <span className="text-muted-foreground">
                Recent invoice numbers ({vendor.historical_invoice_numbers.length} total)
              </span>
              <p className="font-medium font-mono">
                {vendor.historical_invoice_numbers.slice(-5).join(", ")}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function VendorsPage() {
  const { isSignedIn } = useAuth();
  const { hasActiveWorkspace } = useWorkspaceSession();
  const hasWorkspace = hasActiveWorkspace() || isSignedIn;
  const [demoVendors] = useState(() => generateDemoVendors());

  const [search, setSearch] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["vendors"],
    queryFn: () => apiClient.vendors.list(),
    enabled: hasWorkspace,
  });

  const vendors = hasWorkspace ? data?.items ?? [] : demoVendors.items;
  const filtered = search
    ? vendors.filter(
        (v) =>
          v.canonical_name.toLowerCase().includes(search.toLowerCase()) ||
          v.aliases.some((a) => a.toLowerCase().includes(search.toLowerCase()))
      )
    : vendors;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {!hasWorkspace && <WorkspaceGuardDialog open dismissible />}
      <div>
        <h1 className="text-2xl font-semibold">Vendors</h1>
        <p className="text-muted-foreground text-sm mt-1">
          {hasWorkspace
            ? "Canonical vendor names and aliases used for fuzzy matching and deduplication."
            : "Preview data — continue as guest to manage your real vendors."}
        </p>
      </div>

      <div className="flex items-center gap-3">
        <input
          type="search"
          placeholder="Search vendors…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 h-8 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
        />
        <span className="text-sm text-muted-foreground whitespace-nowrap">
          {filtered.length} vendor{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      {hasWorkspace && isLoading && (
        <div className="space-y-2">
          {[1, 2, 3].map((n) => (
            <div key={n} className="h-14 rounded-lg border bg-muted/20 animate-pulse" />
          ))}
        </div>
      )}

      {hasWorkspace && isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          Failed to load vendors.
        </div>
      )}

      {(!hasWorkspace || (!isLoading && !isError)) && filtered.length === 0 && (
        <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground text-sm">
          {search ? "No vendors match your search." : "No vendors found."}
        </div>
      )}

      <div className="space-y-2">
        {filtered.map((vendor) => (
          <VendorRow key={vendor.id} vendor={vendor} readOnly={!hasWorkspace} />
        ))}
      </div>
    </div>
  );
}
