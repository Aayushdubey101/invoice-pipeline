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
import { Button } from "@/components/ui/button";
import { useWorkspaceSession } from "@/contexts/WorkspaceSessionContext";

interface WorkspaceGuardDialogProps {
  open: boolean;
  /** Allow closing via X / backdrop / escape to browse preview data. Upload flow keeps this off. */
  dismissible?: boolean;
}

export function WorkspaceGuardDialog({ open, dismissible = false }: WorkspaceGuardDialogProps) {
  const { createWorkspace } = useWorkspaceSession();
  const [isCreating, setIsCreating] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const handleContinueAsGuest = async () => {
    setIsCreating(true);
    try {
      await createWorkspace();
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <Dialog
      open={open && !dismissed}
      onOpenChange={dismissible ? (next) => { if (!next) setDismissed(true); } : undefined}
    >
      <DialogContent showCloseButton={dismissible}>
        <DialogHeader>
          <DialogTitle>Start a Session to Continue</DialogTitle>
          <DialogDescription>
            Processing documents needs a workspace. Continue as a guest — zero-retention,
            expires in 1 hour, nothing kept unless you download it before the session ends.
            {dismissible && " Or close this to keep browsing with sample data."}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Link href="/sign-in" className="w-full sm:w-auto">
            <Button variant="outline" className="w-full">
              Sign In
            </Button>
          </Link>
          <Button onClick={handleContinueAsGuest} disabled={isCreating} className="w-full sm:w-auto">
            {isCreating ? "Starting..." : "Continue as Guest"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
