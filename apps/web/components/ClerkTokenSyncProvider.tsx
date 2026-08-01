"use client";

import { useEffect, useRef } from "react";
import { useAuth } from "@clerk/nextjs";
import { setClerkToken, markAuthReady, apiClient } from "@/lib/api-client";
import { useProviderSession, type CloudProvider } from "@/contexts/ProviderSessionContext";

export function ClerkTokenSyncProvider({ children }: { children: React.ReactNode }) {
  const { getToken, isSignedIn, isLoaded } = useAuth();
  const readyMarked = useRef(false);
  const wasSignedIn = useRef(false);
  const hydratedForThisSignIn = useRef(false);
  const { resetSession, setProviderConfig, setActiveProvider } = useProviderSession();

  useEffect(() => {
    let interval: NodeJS.Timeout;

    const syncToken = async () => {
      if (isSignedIn) {
        try {
          const token = await getToken();
          setClerkToken(token);
        } catch (error) {
          console.error("Failed to sync Clerk token:", error);
          setClerkToken(null);
        }

        // Auto-load this account's saved cloud-provider config once per
        // sign-in, so it's used immediately without a Settings visit —
        // never the plaintext key itself, just provider/model/hasSavedKey;
        // the backend decrypts its own stored key when none is sent.
        if (!hydratedForThisSignIn.current) {
          hydratedForThisSignIn.current = true;
          try {
            const workspace = await apiClient.workspaces.me();
            const pref = await apiClient.workspaces.getProviderPreference(workspace.id);
            if (pref.provider && pref.model && pref.has_saved_api_key) {
              setProviderConfig(pref.provider as CloudProvider, {
                apiKey: "",
                model: pref.model as string,
                config: (pref.config as Record<string, unknown>) ?? {},
                hasSavedKey: true,
              });
              setActiveProvider(pref.provider as CloudProvider);
            }
          } catch (error) {
            console.error("Failed to hydrate saved provider preference:", error);
          }
        }
      } else {
        setClerkToken(null);
        // Falling edge (was signed in, now signed out): wipe any
        // browser-held LLM config so it's not visible/usable post-logout.
        if (wasSignedIn.current) {
          resetSession();
        }
        hydratedForThisSignIn.current = false;
      }
      wasSignedIn.current = !!isSignedIn;

      if (isLoaded && !readyMarked.current) {
        readyMarked.current = true;
        markAuthReady();
      }
    };

    syncToken();

    if (isSignedIn) {
      // Sync token every 30 seconds to ensure it's fresh
      interval = setInterval(syncToken, 30000);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [getToken, isSignedIn, isLoaded, resetSession, setProviderConfig, setActiveProvider]);

  return <>{children}</>;
}
