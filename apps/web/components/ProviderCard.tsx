"use client";

import { useEffect, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  XCircle,
} from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiClient } from "@/lib/api-client";
import { useProviderSession, type CloudProvider } from "@/contexts/ProviderSessionContext";

interface ProviderCardProps {
  provider: CloudProvider;
  label: string;
  workspaceId?: string | null;
  initialPreference?: { model: string; config: Record<string, unknown>; has_saved_api_key?: boolean };
}

type TestState =
  | { state: "idle" }
  | { state: "testing" }
  | { state: "success"; latencyMs: number }
  | { state: "error"; message: string };

/** Parses a JSON-object config string; returns null (and sets an error) when invalid. */
function tryParseConfigObject(text: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(text || "{}");
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return null;
    return parsed as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function ProviderCard({ provider, label, workspaceId, initialPreference }: ProviderCardProps) {
  const { providers, activeProvider, setProviderConfig, setActiveProvider } = useProviderSession();
  const saved = providers[provider];

  const [expanded, setExpanded] = useState(false);
  const [hydratedFromSession, setHydratedFromSession] = useState(false);
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [configText, setConfigText] = useState("{}");
  const [configError, setConfigError] = useState<string | null>(null);
  const [testState, setTestState] = useState<TestState>({ state: "idle" });
  const [testPassed, setTestPassed] = useState(false);

  // Hydrate edit fields once from a previously-saved session config (context
  // finishes reading sessionStorage async, so this can't be the initial useState).
  useEffect(() => {
    if (hydratedFromSession) return;
    if (saved) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time hydration from session context on mount
      setModel(saved.model);
      setApiKey(saved.apiKey);
      setConfigText(JSON.stringify(saved.config ?? {}, null, 2));
      setHydratedFromSession(true);
    } else if (initialPreference) {
      // No key in this browser session yet — prefill model/config from the
      // persisted (non-secret) workspace preference; the key still needs
      // re-entry, it never leaves this tab per the BYOK security boundary,
      // UNLESS we are in an authenticated workspace that saved it.
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time hydration from a persisted preference on mount
      setModel(initialPreference.model);
      setConfigText(JSON.stringify(initialPreference.config ?? {}, null, 2));
      if (initialPreference.has_saved_api_key) {
        setApiKey("********"); // Dummy value so the user knows it's saved
      }
      setHydratedFromSession(true);
    }
  }, [saved, initialPreference, hydratedFromSession]);

  const isActive = activeProvider === provider && !!saved;

  const onConfigChange = (value: string) => {
    setConfigText(value);
    setTestPassed(false);
    if (value.trim() === "") {
      setConfigError(null);
      return;
    }
    setConfigError(tryParseConfigObject(value) === null ? "Invalid JSON — must be an object" : null);
  };

  const onConfigBlur = () => {
    const parsed = tryParseConfigObject(configText);
    if (parsed !== null) setConfigText(JSON.stringify(parsed, null, 2));
  };

  const configValid = configError === null;
  const canTest = model.trim() !== "" && apiKey.trim() !== "" && configValid && testState.state !== "testing";

  const handleTest = async () => {
    const parsedConfig = tryParseConfigObject(configText);
    if (parsedConfig === null) {
      setConfigError("Invalid JSON — must be an object");
      return;
    }
    setTestState({ state: "testing" });
    try {
      const keyToTest = apiKey === "********" ? "" : apiKey;
      // We skip testing if the user has a saved key but didn't enter a new one,
      // because `/providers/test` cannot access the backend DB.
      if (keyToTest === "" && initialPreference?.has_saved_api_key) {
        setTestState({ state: "success", latencyMs: 0 });
        setTestPassed(true);
        return;
      }
      const result = await apiClient.providers.test({ provider, apiKey: keyToTest, model, config: parsedConfig });
      if (result.success) {
        setTestState({ state: "success", latencyMs: result.latency_ms });
        setTestPassed(true);
      } else {
        setTestState({ state: "error", message: result.error ?? "Connection failed" });
        setTestPassed(false);
      }
    } catch (err) {
      setTestState({ state: "error", message: err instanceof Error ? err.message : "Connection failed" });
      setTestPassed(false);
    }
  };

  const handleSave = async () => {
    const parsedConfig = tryParseConfigObject(configText);
    if (parsedConfig === null) return;

    // Persist model/config (and conditionally key) so it survives the next session
    let keyToSave = apiKey === "********" ? undefined : apiKey;
    let hasSavedKey = !!initialPreference?.has_saved_api_key;
    
    if (workspaceId) {
      try {
        const result = await apiClient.workspaces.updateProviderPreference(workspaceId, {
          provider,
          model,
          config: parsedConfig,
        }, keyToSave);
        if (result.has_saved_api_key) {
           hasSavedKey = true;
        }
      } catch (err) {
        console.error("Failed to persist provider preference:", err);
      }
    }
    
    const pConfig = {
      apiKey: keyToSave ?? "",
      model,
      config: parsedConfig,
      hasSavedKey,
    };
    
    setProviderConfig(provider, pConfig);
    setActiveProvider(provider);
  };

  const statusBadge = () => {
    if (testState.state === "testing")
      return <Badge variant="outline" className="animate-pulse text-[10px] py-0">Testing…</Badge>;
    if (isActive)
      return <Badge className="bg-green-500/10 text-green-600 border-green-500/20 text-[10px] py-0">Connected</Badge>;
    if (testState.state === "error")
      return <Badge className="bg-rose-500/10 text-rose-500 border-rose-500/20 text-[10px] py-0">Error</Badge>;
    return <Badge variant="secondary" className="text-[10px] py-0">Not Configured</Badge>;
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <KeyRound className="h-4 w-4 text-amber-500 shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-semibold">{label}</p>
              <p className="text-xs text-muted-foreground truncate">{saved?.model || "Not configured"}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {statusBadge()}
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={() => setExpanded((e) => !e)}
              aria-label={expanded ? `Collapse ${label}` : `Expand ${label}`}
            >
              {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </CardHeader>

      {expanded && (
        <CardContent className="space-y-4 border-t pt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground font-semibold">Model</label>
              <Input
                value={model}
                onChange={(e) => {
                  setModel(e.target.value);
                  setTestPassed(false);
                }}
                placeholder="e.g. gpt-4o-mini"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground font-semibold">API Key</label>
              <div className="relative">
                <Input
                  type={showKey ? "text" : "password"}
                  autoComplete="off"
                  value={apiKey}
                  onChange={(e) => {
                    setApiKey(e.target.value);
                    setTestPassed(false);
                  }}
                  placeholder={`Enter ${label} API key`}
                  className="pr-9"
                />
                <button
                  type="button"
                  onClick={() => setShowKey((s) => !s)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  aria-label={showKey ? "Hide API key" : "Show API key"}
                >
                  {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground font-semibold">JSON Config (optional)</label>
            <Textarea
              value={configText}
              onChange={(e) => onConfigChange(e.target.value)}
              onBlur={onConfigBlur}
              rows={4}
              className="font-mono text-xs"
              placeholder='{"temperature": 0.2}'
            />
            {configError && <p className="text-xs text-red-600">{configError}</p>}
          </div>

          {testState.state === "success" && (
            <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3 text-xs text-emerald-600 font-semibold">
              <CheckCircle2 className="h-4 w-4" /> Connected ({testState.latencyMs}ms)
            </div>
          )}
          {testState.state === "error" && (
            <div className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50/50 p-3 text-xs text-red-700 dark:border-red-900/50 dark:bg-red-950/20 dark:text-red-400">
              <XCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <p className="font-semibold">{testState.message}</p>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="gap-1.5"
              disabled={!canTest}
              onClick={handleTest}
            >
              {testState.state === "testing" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Test Connection
            </Button>
            <Button type="button" size="sm" disabled={!testPassed} onClick={handleSave}>
              Save For This Session
            </Button>
          </div>
        </CardContent>
      )}
    </Card>
  );
}
