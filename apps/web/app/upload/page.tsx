"use client";

import { useAuth } from "@clerk/nextjs";
import { useQuery } from "@tanstack/react-query";
import { BatchUploadDropzone } from "@/components/BatchUploadDropzone";
import { ProviderGuardDialog } from "@/components/ProviderGuardDialog";
import { WorkspaceGuardDialog } from "@/components/WorkspaceGuardDialog";
import { useProviderSession } from "@/contexts/ProviderSessionContext";
import { useWorkspaceSession } from "@/contexts/WorkspaceSessionContext";
import { apiClient } from "@/lib/api-client";

export default function UploadPage() {
  const { isSignedIn } = useAuth();
  const { hasSessionProvider } = useProviderSession();
  const { hasActiveWorkspace } = useWorkspaceSession();
  const { data: llmStatus, isLoading } = useQuery({
    queryKey: ["llm-status"],
    queryFn: () => apiClient.llm.status(),
  });

  const hasWorkspace = hasActiveWorkspace() || isSignedIn;
  const hasServerProvider = llmStatus != null && llmStatus.provider !== "none";
  const canUpload = hasWorkspace && (hasSessionProvider() || hasServerProvider);

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-semibold mb-1">Upload Invoices</h1>
        <p className="text-muted-foreground text-sm">
          Single file, multiple files, or an entire folder. PDF, PNG, JPEG, TIFF.
          Each file enters the AI pipeline independently — failures don&apos;t stop others.
        </p>
      </div>
      {isLoading ? null : !hasWorkspace ? (
        <WorkspaceGuardDialog open />
      ) : canUpload ? (
        <BatchUploadDropzone />
      ) : (
        <ProviderGuardDialog open />
      )}
    </div>
  );
}
