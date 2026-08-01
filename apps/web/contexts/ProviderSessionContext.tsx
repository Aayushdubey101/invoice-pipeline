"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type CloudProvider = "openai" | "anthropic" | "gemini" | "groq";

export interface ProviderConfig {
  apiKey: string;
  model: string;
  config: Record<string, unknown>;
  hasSavedKey?: boolean;
}

type ProviderMap = Partial<Record<CloudProvider, ProviderConfig>>;

const STORAGE_KEY = "invoice_pipeline_provider_session";

interface StoredSession {
  providers: ProviderMap;
  activeProvider: CloudProvider | null;
}

interface ProviderSessionContextValue {
  providers: ProviderMap;
  activeProvider: CloudProvider | null;
  setProviderConfig: (provider: CloudProvider, config: ProviderConfig) => void;
  clearProviderConfig: (provider: CloudProvider) => void;
  setActiveProvider: (provider: CloudProvider | null) => void;
  hasSessionProvider: () => boolean;
  /** Wipe every provider's config from both state and sessionStorage — call
   * on logout and on guest Finish Session so no key/model lingers in the UI
   * past the session it was entered in. */
  resetSession: () => void;
}

const ProviderSessionContext = createContext<ProviderSessionContextValue | null>(null);

function readSession(): StoredSession {
  if (typeof window === "undefined") return { providers: {}, activeProvider: null };
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return { providers: {}, activeProvider: null };
    const parsed = JSON.parse(raw) as Partial<StoredSession>;
    return { providers: parsed.providers ?? {}, activeProvider: parsed.activeProvider ?? null };
  } catch {
    return { providers: {}, activeProvider: null };
  }
}

export function ProviderSessionProvider({ children }: { children: React.ReactNode }) {
  const [providers, setProviders] = useState<ProviderMap>({});
  const [activeProvider, setActiveProviderState] = useState<CloudProvider | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const session = readSession();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time hydration from sessionStorage on mount
    setProviders(session.providers);
    setActiveProviderState(session.activeProvider);
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated || typeof window === "undefined") return;
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ providers, activeProvider }));
  }, [providers, activeProvider, hydrated]);

  const value = useMemo<ProviderSessionContextValue>(
    () => ({
      providers,
      activeProvider,
      setProviderConfig: (provider, config) =>
        setProviders((prev) => ({ ...prev, [provider]: config })),
      clearProviderConfig: (provider) =>
        setProviders((prev) => {
          const next = { ...prev };
          delete next[provider];
          return next;
        }),
      setActiveProvider: (provider) => setActiveProviderState(provider),
      hasSessionProvider: () => {
        if (!activeProvider) return false;
        const p = providers[activeProvider];
        if (!p) return false;
        return (p.apiKey.trim() !== "" || !!p.hasSavedKey) && p.model.trim() !== "";
      },
      resetSession: () => {
        setProviders({});
        setActiveProviderState(null);
        if (typeof window !== "undefined") {
          window.sessionStorage.removeItem(STORAGE_KEY);
        }
      },
    }),
    [providers, activeProvider]
  );

  return (
    <ProviderSessionContext.Provider value={value}>{children}</ProviderSessionContext.Provider>
  );
}

export function useProviderSession(): ProviderSessionContextValue {
  const ctx = useContext(ProviderSessionContext);
  if (!ctx) throw new Error("useProviderSession must be used within a ProviderSessionProvider");
  return ctx;
}
