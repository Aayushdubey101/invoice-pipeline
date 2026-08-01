"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  Sparkles,
  Layers,
  ClipboardCheck,
  Gauge,
  Building2,
  FileSpreadsheet,
  ArrowRight,
  Check,
  Upload,
  LayoutGrid,
  LayoutDashboard,
} from "lucide-react";
import { useAuth } from "@clerk/nextjs";
import { useWorkspaceSession } from "@/contexts/WorkspaceSessionContext";

const features = [
  {
    icon: Sparkles,
    title: "AI Invoice Extraction",
    description: "LLM-powered extraction pulls structured fields and line items from any invoice format.",
  },
  {
    icon: Layers,
    title: "Batch Processing",
    description: "Upload a single file, multiple files, or an entire folder. Each invoice processes independently.",
  },
  {
    icon: ClipboardCheck,
    title: "Human Review Queue",
    description: "Low-confidence fields are flagged for review with jump-to-source highlighting on the original document.",
  },
  {
    icon: Gauge,
    title: "Confidence Scoring",
    description: "Every extraction carries a weighted, multi-signal confidence score across OCR, LLM, and validation checks.",
  },
  {
    icon: Building2,
    title: "Vendor Intelligence",
    description: "Fuzzy matching and embeddings canonicalize vendor names and learn preferences over time.",
  },
  {
    icon: FileSpreadsheet,
    title: "Excel Export",
    description: "Export validated, review-approved results to Excel — filtered by batch, vendor, or date range.",
  },
];

const services = [
  { href: "/upload", label: "Upload Invoices", icon: Upload },
  { href: "/batches", label: "Batches", icon: LayoutGrid },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
];

export default function Home() {
  const router = useRouter();
  const { createWorkspace, hasActiveWorkspace } = useWorkspaceSession();
  const { isSignedIn } = useAuth();
  const [isStarting, setIsStarting] = useState(false);

  const handleContinueAsGuest = async () => {
    setIsStarting(true);
    try {
      if (!hasActiveWorkspace()) await createWorkspace();
      router.push("/upload");
    } finally {
      setIsStarting(false);
    }
  };

  const isGuest = !isSignedIn && hasActiveWorkspace();

  return (
    <div className="max-w-5xl mx-auto space-y-12">
      {/* Hero */}
      <section className="text-center space-y-6 pt-6">
        <h1 className="text-4xl md:text-5xl font-bold tracking-tight">Invoice Intelligence Platform</h1>
        <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
          Extract structured invoice data using AI, review low-confidence fields, process batch
          uploads, and export validated results.
        </p>

        {isSignedIn ? (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2 max-w-2xl mx-auto">
            {services.map((s) => (
              <Link key={s.href} href={s.href} className="block">
                <div className="border rounded-lg p-5 space-y-2 bg-card text-left hover:border-primary transition-colors h-full">
                  <s.icon className="h-6 w-6 text-primary" />
                  <h2 className="font-semibold">{s.label}</h2>
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <div className="flex flex-col sm:flex-row gap-4 justify-center pt-2 max-w-xl mx-auto">
            {isGuest ? (
              <div className="flex-1 border rounded-lg p-5 space-y-3 bg-card text-left">
                <h2 className="font-semibold">Continue Your Session</h2>
                <ul className="text-sm text-muted-foreground space-y-1">
                  {["Guest session active", "Zero retention", "Expires in 1 hour"].map((item) => (
                    <li key={item} className="flex items-center gap-2">
                      <Check className="h-3.5 w-3.5 text-primary shrink-0" /> {item}
                    </li>
                  ))}
                </ul>
                <Link href="/upload" className="block w-full">
                  <Button className="w-full gap-2">
                    Upload Invoices
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
              </div>
            ) : (
              <div className="flex-1 border rounded-lg p-5 space-y-3 bg-card text-left">
                <h2 className="font-semibold">Continue as Guest</h2>
                <ul className="text-sm text-muted-foreground space-y-1">
                  {["No account", "Zero retention", "Privacy-first"].map((item) => (
                    <li key={item} className="flex items-center gap-2">
                      <Check className="h-3.5 w-3.5 text-primary shrink-0" /> {item}
                    </li>
                  ))}
                </ul>
                <Button onClick={handleContinueAsGuest} disabled={isStarting} className="w-full gap-2">
                  {isStarting ? "Starting..." : "Continue as Guest"}
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            )}

            <div className="flex-1 border rounded-lg p-5 space-y-3 bg-card text-left">
              <h2 className="font-semibold">Sign In</h2>
              <ul className="text-sm text-muted-foreground space-y-1">
                {["Save projects", "Resume work", "Dashboard & history"].map((item) => (
                  <li key={item} className="flex items-center gap-2">
                    <Check className="h-3.5 w-3.5 text-primary shrink-0" /> {item}
                  </li>
                ))}
              </ul>
              <Link href="/sign-in" className="block w-full">
                <Button variant="outline" className="w-full">
                  Sign In
                </Button>
              </Link>
            </div>
          </div>
        )}
      </section>

      {/* Features */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {features.map((f) => (
          <div key={f.title} className="border rounded-lg p-5 space-y-2 bg-card h-full">
            <f.icon className="h-7 w-7 text-primary" />
            <h3 className="font-semibold">{f.title}</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">{f.description}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
