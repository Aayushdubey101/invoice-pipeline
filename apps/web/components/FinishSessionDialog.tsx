"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api-client";
import { useWorkspaceSession } from "@/contexts/WorkspaceSessionContext";
import { useProviderSession } from "@/contexts/ProviderSessionContext";

interface FinishSessionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type Status = "idle" | "downloading" | "ready" | "error";

function triggerDownload(blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "invoice-session-export.zip";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function FinishSessionDialog({ open, onOpenChange }: FinishSessionDialogProps) {
  const router = useRouter();
  const { clearWorkspace } = useWorkspaceSession();
  const { resetSession } = useProviderSession();
  const [status, setStatus] = useState<Status>("idle");

  useEffect(() => {
    if (!open) {
      setStatus("idle");
      return;
    }
    setStatus("downloading");
    apiClient.session
      .finish()
      .then((blob) => {
        triggerDownload(blob);
        setStatus("ready");
      })
      .catch(() => setStatus("error"));
  }, [open]);

  const handleDone = () => {
    resetSession();
    clearWorkspace();
    onOpenChange(false);
    router.push("/");
  };

  return (
    <Dialog open={open}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>Your Session Is Complete</DialogTitle>
          <DialogDescription>
            {status === "downloading" && "Preparing your export…"}
            {status === "ready" &&
              "Your download has started. Once it's saved, everything from this session — documents, data, and files — will be permanently deleted."}
            {status === "error" &&
              "Something went wrong generating your export. You can try again or leave without downloading."}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button onClick={handleDone} disabled={status === "downloading"}>
            {status === "downloading"
              ? "Preparing..."
              : status === "error"
                ? "Leave Anyway"
                : "Download & Finish"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
