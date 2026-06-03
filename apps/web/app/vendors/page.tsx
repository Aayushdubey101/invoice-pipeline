"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Check, X, Building2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api-client";
import type { Vendor } from "@/lib/types";

const STATUS_BADGE: Record<string, string> = {
  active: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  pending_review: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300",
  inactive: "bg-muted text-muted-foreground",
};

interface EditState {
  canonical_name: string;
  aliases: string;
}

function VendorRow({ vendor }: { vendor: Vendor }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
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

  return (
    <div className="flex items-start gap-3 px-4 py-3 rounded-lg border bg-card group">
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
            <div className="flex items-center gap-2">
              <span className="font-medium text-sm">{vendor.canonical_name}</span>
              <span
                className={cn(
                  "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium",
                  STATUS_BADGE[vendor.status] ?? STATUS_BADGE.inactive
                )}
              >
                {vendor.status.replace("_", " ")}
              </span>
            </div>
            {vendor.aliases.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Also known as: {vendor.aliases.join(", ")}
              </p>
            )}
          </>
        )}
      </div>
      {!editing && (
        <button
          onClick={() => setEditing(true)}
          className="invisible group-hover:visible h-7 w-7 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-muted shrink-0"
          aria-label={`Edit ${vendor.canonical_name}`}
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

export default function VendorsPage() {
  const [search, setSearch] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["vendors"],
    queryFn: () => apiClient.vendors.list(),
  });

  const vendors = data?.items ?? [];
  const filtered = search
    ? vendors.filter(
        (v) =>
          v.canonical_name.toLowerCase().includes(search.toLowerCase()) ||
          v.aliases.some((a) => a.toLowerCase().includes(search.toLowerCase()))
      )
    : vendors;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Vendors</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Canonical vendor names and aliases used for fuzzy matching and deduplication.
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

      {isLoading && (
        <div className="space-y-2">
          {[1, 2, 3].map((n) => (
            <div key={n} className="h-14 rounded-lg border bg-muted/20 animate-pulse" />
          ))}
        </div>
      )}

      {isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          Failed to load vendors.
        </div>
      )}

      {!isLoading && !isError && filtered.length === 0 && (
        <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground text-sm">
          {search ? "No vendors match your search." : "No vendors found."}
        </div>
      )}

      <div className="space-y-2">
        {filtered.map((vendor) => (
          <VendorRow key={vendor.id} vendor={vendor} />
        ))}
      </div>
    </div>
  );
}
