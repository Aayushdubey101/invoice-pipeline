import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Upload, ClipboardList, Building2, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

const features = [
  {
    icon: Upload,
    title: "Multi-format Ingestion",
    description: "Text PDFs, scanned PDFs, images, and email bodies with attachments.",
  },
  {
    icon: ClipboardList,
    title: "Per-field Confidence",
    description: "Every extracted field carries a confidence score and verbatim evidence snippet.",
  },
  {
    icon: Building2,
    title: "Vendor Canonicalization",
    description: "Fuzzy matching + embeddings resolve spelling variants to a single vendor ID.",
  },
];

const pipeline = [
  "Ingest", "Classify", "Extract Text", "OCR", "LLM Extraction",
  "Confidence Score", "Canonicalize", "Persist", "Notify",
];

export default function Home() {
  return (
    <div className="max-w-4xl mx-auto space-y-16">
      {/* Hero */}
      <section className="text-center space-y-4 pt-8">
        <Badge variant="outline" className="text-xs">Phase 1 — Foundation</Badge>
        <h1 className="text-4xl font-bold tracking-tight">Invoice Intelligence Pipeline</h1>
        <p className="text-sm text-muted-foreground">by Aayush Dubey</p>
        <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
          Ingest unstructured invoices. Extract structured, canonicalized financial data.
          Review low-confidence fields with a human-in-the-loop UI.
        </p>
        <div className="flex gap-3 justify-center pt-2">
          <Link href="/upload" className={cn(buttonVariants({ variant: "default" }), "gap-2")}>
            Upload Invoice <ArrowRight className="h-4 w-4" />
          </Link>
          <Link href="/review" className={cn(buttonVariants({ variant: "outline" }))}>
            Review Queue
          </Link>
        </div>
      </section>

      {/* Features */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {features.map((f) => (
          <div key={f.title} className="border rounded-lg p-5 space-y-2 bg-card">
            <f.icon className="h-8 w-8 text-primary" />
            <h3 className="font-semibold">{f.title}</h3>
            <p className="text-sm text-muted-foreground">{f.description}</p>
          </div>
        ))}
      </section>

      {/* Pipeline */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Pipeline Stages</h2>
        <div className="flex flex-wrap gap-2">
          {pipeline.map((stage, i) => (
            <span key={stage} className="flex items-center gap-1">
              <Badge variant="secondary" className="text-xs">{stage}</Badge>
              {i < pipeline.length - 1 && (
                <span className="text-muted-foreground text-xs">→</span>
              )}
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}
