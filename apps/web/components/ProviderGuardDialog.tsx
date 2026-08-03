"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { buttonVariants } from "@/components/ui/button";

interface ProviderGuardDialogProps {
  open: boolean;
  /** Allow closing via X / backdrop / escape to browse without a provider configured. */
  dismissible?: boolean;
}

export function ProviderGuardDialog({ open, dismissible = false }: ProviderGuardDialogProps) {
  const [dismissed, setDismissed] = useState(false);

  return (
    <Dialog
      open={open && !dismissed}
      onOpenChange={dismissible ? (next) => { if (!next) setDismissed(true); } : undefined}
    >
      <DialogContent showCloseButton={dismissible}>
        <DialogHeader>
          <DialogTitle>No AI Provider Configured</DialogTitle>
          <DialogDescription>
            To process documents you must configure an AI Provider. Read our setup guide.
            {dismissible && " Or close this to keep browsing."}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Link href="/docs" className={buttonVariants({ variant: "outline" })}>
            Open Documentation
          </Link>
          <Link href="/settings" className={buttonVariants({ variant: "default" })}>
            Configure Provider
          </Link>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
