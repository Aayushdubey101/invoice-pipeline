"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button, buttonVariants } from "@/components/ui/button";

const WELCOME_SEEN_KEY = "invoice_pipeline_welcome_seen";

const STEPS = [
  "Configure AI Provider",
  "Test Connection",
  "Upload Invoice",
  "Review Results",
  "Export Excel",
];

export function WelcomeModal() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time check of localStorage on mount
    if (!localStorage.getItem(WELCOME_SEEN_KEY)) setOpen(true);
  }, []);

  const dismiss = () => {
    localStorage.setItem(WELCOME_SEEN_KEY, "1");
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) dismiss(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invoice Intelligence Platform</DialogTitle>
          <DialogDescription>Structured extraction from unstructured invoices, with human review.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <p className="text-sm font-medium">To begin:</p>
          <ol className="list-decimal list-inside text-sm text-muted-foreground space-y-1">
            {STEPS.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </div>
        <DialogFooter>
          <Link href="/docs" onClick={dismiss} className={buttonVariants({ variant: "outline" })}>
            Open Docs
          </Link>
          <Link href="/settings" onClick={dismiss} className={buttonVariants({ variant: "outline" })}>
            Configure Provider
          </Link>
          <Button onClick={dismiss}>Continue</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
