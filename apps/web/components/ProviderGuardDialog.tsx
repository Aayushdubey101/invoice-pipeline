"use client";

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
}

export function ProviderGuardDialog({ open }: ProviderGuardDialogProps) {
  return (
    <Dialog open={open}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>No AI Provider Configured</DialogTitle>
          <DialogDescription>
            To process documents you must configure an AI Provider. Read our setup guide.
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
