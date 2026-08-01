"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState } from "react";
import { ProviderSessionProvider } from "@/contexts/ProviderSessionContext";
import { WorkspaceSessionProvider } from "@/contexts/WorkspaceSessionContext";
import { WelcomeModal } from "@/components/WelcomeModal";
import { ClerkTokenSyncProvider } from "@/components/ClerkTokenSyncProvider";
import { MergeAccountDialog } from "@/components/MergeAccountDialog";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <QueryClientProvider client={queryClient}>
        <ProviderSessionProvider>
          <WorkspaceSessionProvider>
            <ClerkTokenSyncProvider>
              <WelcomeModal />
              <MergeAccountDialog />
              {children}
            </ClerkTokenSyncProvider>
          </WorkspaceSessionProvider>
        </ProviderSessionProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
