"use client";

import { useAuth } from "@clerk/nextjs";
import { useWorkspaceSession } from "@/contexts/WorkspaceSessionContext";
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export function MergeAccountDialog() {
  const { isSignedIn, isLoaded } = useAuth();
  const { hasActiveWorkspace, workspaceId, clearWorkspace } = useWorkspaceSession();
  const [open, setOpen] = useState(false);
  const [isMerging, setIsMerging] = useState(false);

  useEffect(() => {
    // If they just signed in and STILL have an active guest workspace ID in sessionStorage
    if (isLoaded && isSignedIn && hasActiveWorkspace() && workspaceId) {
      setOpen(true);
    }
  }, [isLoaded, isSignedIn, hasActiveWorkspace, workspaceId]);

  const handleMerge = async () => {
    if (!workspaceId) return;
    try {
      setIsMerging(true);
      await apiClient.workspaces.migrate(workspaceId);
      clearWorkspace(); // Clear local storage after successful migration
      setOpen(false);
    } catch (e) {
      console.error("Migration failed", e);
    } finally {
      setIsMerging(false);
    }
  };

  const handleDismiss = () => {
    clearWorkspace();
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={(val) => {
        if (!val) handleDismiss();
    }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Merge Guest Data?</DialogTitle>
          <DialogDescription>
            You have in-progress invoices and data from your guest session. Would you like to merge this data into your account?
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={handleDismiss} disabled={isMerging}>
            Discard Data
          </Button>
          <Button onClick={handleMerge} disabled={isMerging}>
            {isMerging ? "Merging..." : "Merge Data"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
