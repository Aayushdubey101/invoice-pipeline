"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { apiClient, setWorkspaceId as syncApiWorkspaceId } from "@/lib/api-client";

const STORAGE_KEY = "invoice_pipeline_workspace_session";

interface StoredSession {
  workspaceId: string | null;
  expiresAt: string | null;
}

interface WorkspaceSessionContextValue {
  workspaceId: string | null;
  expiresAt: string | null;
  isExpired: () => boolean;
  hasActiveWorkspace: () => boolean;
  createWorkspace: () => Promise<string>;
  clearWorkspace: () => void;
}

const WorkspaceSessionContext = createContext<WorkspaceSessionContextValue | null>(null);

function readSession(): StoredSession {
  if (typeof window === "undefined") return { workspaceId: null, expiresAt: null };
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return { workspaceId: null, expiresAt: null };
    const parsed = JSON.parse(raw) as Partial<StoredSession>;
    return { workspaceId: parsed.workspaceId ?? null, expiresAt: parsed.expiresAt ?? null };
  } catch {
    return { workspaceId: null, expiresAt: null };
  }
}

export function WorkspaceSessionProvider({ children }: { children: React.ReactNode }) {
  const [workspaceId, setWorkspaceIdState] = useState<string | null>(null);
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const session = readSession();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time hydration from sessionStorage on mount
    setWorkspaceIdState(session.workspaceId);
    setExpiresAt(session.expiresAt);
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated || typeof window === "undefined") return;
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ workspaceId, expiresAt }));
    syncApiWorkspaceId(workspaceId);
  }, [workspaceId, expiresAt, hydrated]);

  const value = useMemo<WorkspaceSessionContextValue>(() => {
    const isExpired = () => {
      if (!expiresAt) return false;
      return new Date(expiresAt).getTime() < Date.now();
    };

    return {
      workspaceId,
      expiresAt,
      isExpired,
      hasActiveWorkspace: () => workspaceId !== null && !isExpired(),
      createWorkspace: async () => {
        const ws = await apiClient.workspaces.create();
        setWorkspaceIdState(ws.id);
        setExpiresAt(ws.expires_at);
        return ws.id;
      },
      clearWorkspace: () => {
        setWorkspaceIdState(null);
        setExpiresAt(null);
      },
    };
  }, [workspaceId, expiresAt]);

  return (
    <WorkspaceSessionContext.Provider value={value}>{children}</WorkspaceSessionContext.Provider>
  );
}

export function useWorkspaceSession(): WorkspaceSessionContextValue {
  const ctx = useContext(WorkspaceSessionContext);
  if (!ctx) throw new Error("useWorkspaceSession must be used within a WorkspaceSessionProvider");
  return ctx;
}
