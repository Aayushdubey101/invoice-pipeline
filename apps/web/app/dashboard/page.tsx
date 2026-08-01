"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import {
  BarChart3,
  CheckCircle2,
  AlertCircle,
  Clock,
  FileText,
  Layers,
  TrendingUp,
  Download,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { apiClient, type DashboardStats } from "@/lib/api-client";
import { WorkspaceGuardDialog } from "@/components/WorkspaceGuardDialog";
import { useWorkspaceSession } from "@/contexts/WorkspaceSessionContext";
import { generateDemoDashboardStats } from "@/lib/demo-data";

function StatCard({
  label,
  value,
  icon: Icon,
  color = "text-foreground",
  href,
}: {
  label: string;
  value: number | string;
  icon: React.ElementType;
  color?: string;
  href?: string;
}) {
  const content = (
    <div className="rounded-lg border bg-card p-5 space-y-2 hover:shadow-sm transition-shadow">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground font-medium uppercase tracking-wide">
          {label}
        </span>
        <Icon className={cn("h-4 w-4", color)} />
      </div>
      <p className={cn("text-3xl font-bold tabular-nums", color)}>{value}</p>
    </div>
  );
  return href ? <Link href={href}>{content}</Link> : content;
}

function ExcelExportPanel({ disabled = false }: { disabled?: boolean }) {
  const [downloading, setDownloading] = useState(false);
  const [reviewFilter, setReviewFilter] = useState("all");

  const handleExport = () => {
    setDownloading(true);
    const url = apiClient.export.excel({
      reviewStatus: reviewFilter === "all" ? undefined : reviewFilter,
    });
    // Trigger download via invisible anchor
    const a = document.createElement("a");
    a.href = url;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => setDownloading(false), 2000);
  };

  return (
    <div className="rounded-lg border bg-card p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Download className="h-4 w-4 text-muted-foreground" />
        <h3 className="font-semibold text-sm">Export to Excel</h3>
      </div>

      <div className="space-y-3">
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">Filter by review status</label>
          <select
            id="review-filter"
            value={reviewFilter}
            onChange={(e) => setReviewFilter(e.target.value)}
            className="w-full rounded-md border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="all">All invoices</option>
            <option value="needs_review">Needs review only</option>
            <option value="approved">Approved only</option>
          </select>
        </div>

        <Button onClick={handleExport} disabled={downloading || disabled} className="w-full gap-2" size="sm">
          <Download className="h-4 w-4" />
          {downloading ? "Preparing download…" : "Download Excel"}
        </Button>

        <p className="text-xs text-muted-foreground">
          {disabled
            ? "Continue as guest to export real data."
            : "Exports Invoice Summary + Line Items sheets. All fields and confidence scores included."}
        </p>
      </div>
    </div>
  );
}

function DashboardBody({
  stats,
  onRefresh,
  isDemo,
}: {
  stats: DashboardStats;
  onRefresh: () => void;
  isDemo: boolean;
}) {
  const { totals, recent_uploads, vendor_statistics } = stats;
  return (
    <>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Business Dashboard</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {isDemo ? "Preview data — continue as guest for real-time numbers" : "Real-time pipeline overview and export controls"}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={onRefresh} className="gap-2">
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Invoices" value={totals.invoices} icon={FileText} href="/dashboard" />
        <StatCard
          label="Needs Review"
          value={totals.needs_review}
          icon={AlertCircle}
          color={totals.needs_review > 0 ? "text-yellow-600" : "text-foreground"}
          href="/review"
        />
        <StatCard label="Approved" value={totals.approved} icon={CheckCircle2} color="text-green-600" />
        <StatCard label="Batches" value={totals.batches} icon={Layers} href="/batches" />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Completed" value={totals.complete_documents} icon={CheckCircle2} color="text-green-600" />
        <StatCard
          label="Processing"
          value={totals.processing_documents}
          icon={Clock}
          color={totals.processing_documents > 0 ? "text-blue-600" : "text-foreground"}
        />
        <StatCard
          label="Failed"
          value={totals.failed_documents}
          icon={AlertCircle}
          color={totals.failed_documents > 0 ? "text-red-600" : "text-foreground"}
        />
        <StatCard label="Top Vendors" value={vendor_statistics.length} icon={TrendingUp} />
      </div>

      {/* Main content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent uploads */}
        <div className="lg:col-span-2 rounded-lg border bg-card overflow-hidden">
          <div className="px-5 py-3 border-b flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <h3 className="font-semibold text-sm">Recent Uploads</h3>
          </div>
          {recent_uploads.length === 0 ? (
            <div className="px-5 py-10 text-center text-sm text-muted-foreground">
              No uploads yet. <Link href="/upload" className="text-primary hover:underline">Upload invoices →</Link>
            </div>
          ) : (
            <div className="divide-y text-sm">
              {recent_uploads.map((doc) => (
                <div key={doc.document_id} className="flex items-center gap-3 px-5 py-3">
                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="flex-1 min-w-0">
                    <p className="truncate font-medium">{doc.filename}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {new Date(doc.created_at).toLocaleString()}
                      {doc.batch_id && (
                        <> · <Link href="/batches" className="hover:underline">batch</Link></>
                      )}
                    </p>
                  </div>
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium border shrink-0",
                      doc.status === "complete"
                        ? "bg-green-100 text-green-700 border-green-200"
                        : doc.status === "failed"
                        ? "bg-red-100 text-red-700 border-red-200"
                        : "bg-yellow-100 text-yellow-700 border-yellow-200"
                    )}
                  >
                    {doc.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Vendor stats */}
          {vendor_statistics.length > 0 && (
            <div className="rounded-lg border bg-card overflow-hidden">
              <div className="px-5 py-3 border-b flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-muted-foreground" />
                <h3 className="font-semibold text-sm">Top Vendors</h3>
              </div>
              <div className="p-4 space-y-2">
                {vendor_statistics.slice(0, 6).map((v) => {
                  const max = vendor_statistics[0].invoice_count;
                  const pct = Math.round((v.invoice_count / max) * 100);
                  return (
                    <div key={v.vendor_name} className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="truncate">{v.vendor_name}</span>
                        <span className="text-muted-foreground shrink-0 ml-2">
                          {v.invoice_count}
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                        <div className="h-full bg-primary rounded-full" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Excel Export */}
          <ExcelExportPanel disabled={isDemo} />
        </div>
      </div>
    </>
  );
}

export default function DashboardPage() {
  const { isSignedIn } = useAuth();
  const { hasActiveWorkspace } = useWorkspaceSession();
  const hasWorkspace = hasActiveWorkspace() || isSignedIn;
  const [demoStats, setDemoStats] = useState(() => generateDemoDashboardStats());

  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.dashboard.stats();
      setStats(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load stats");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (hasWorkspace) load();
  }, [hasWorkspace]);

  if (!hasWorkspace) {
    return (
      <div className="max-w-5xl mx-auto space-y-8">
        <WorkspaceGuardDialog open dismissible />
        <DashboardBody
          stats={demoStats}
          onRefresh={() => setDemoStats(generateDemoDashboardStats())}
          isDemo
        />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto space-y-6 animate-pulse">
        <div className="h-8 w-48 rounded bg-muted" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="rounded-lg border bg-card p-5 h-24" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      </div>
    );
  }

  if (!stats) return null;

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      <DashboardBody stats={stats} onRefresh={load} isDemo={false} />
    </div>
  );
}
