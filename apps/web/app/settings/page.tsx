"use client";

import { useEffect, useState } from "react";
import {
  Cpu,
  Settings as SettingsIcon,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Database,
  Server,
  ShieldCheck,
  Sparkles,
  CloudCog,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ProviderCard } from "@/components/ProviderCard";
import { apiClient, type AppSettings, type ProviderPreference, type SettingsUpdatePayload } from "@/lib/api-client";
import type { CloudProvider } from "@/contexts/ProviderSessionContext";

interface LLMStatus {
  provider: string;
  model: string;
  endpoint: string | null;
}

type LocalServerTest =
  | { state: "idle" }
  | { state: "testing" }
  | { state: "online"; models: string[] }
  | { state: "offline"; message: string };

type LlamaCppTest =
  | { state: "idle" }
  | { state: "testing" }
  | { state: "online"; latency_ms?: number; endpoint?: string; models: string[] }
  | { state: "offline"; message: string; endpoint?: string };

const LOCAL_PROVIDERS = [
  { id: "ollama", name: "Ollama" },
  { id: "lm_studio", name: "LM Studio" },
  { id: "llamacpp", name: "llama.cpp" },
] as const;

const CLOUD_PROVIDERS: { id: CloudProvider; name: string }[] = [
  { id: "openai", name: "OpenAI" },
  { id: "anthropic", name: "Anthropic" },
  { id: "gemini", name: "Google Gemini" },
  { id: "groq", name: "Groq" },
];

export default function SettingsPage() {
  const [status, setStatus] = useState<LLMStatus | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [providerPreference, setProviderPreference] = useState<ProviderPreference | null>(null);

  const [selectedProvider, setSelectedProvider] = useState<string>("auto");

  // LM Studio
  const [lmStudioModel, setLmStudioModel] = useState<string>("");
  const [lmStudioBaseUrl, setLmStudioBaseUrl] = useState<string>("");
  const [lmStudioTest, setLmStudioTest] = useState<LocalServerTest>({ state: "idle" });

  // Ollama
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState<string>("");
  const [ollamaModel, setOllamaModel] = useState<string>("");
  const [ollamaTest, setOllamaTest] = useState<LocalServerTest>({ state: "idle" });

  // llama.cpp
  const [llamacppBaseUrl, setLlamacppBaseUrl] = useState<string>("");
  const [llamacppModel, setLlamacppModel] = useState<string>("");
  const [llamacppKey, setLlamacppKey] = useState<string>("");
  const [llamacppContextLength, setLlamacppContextLength] = useState<number>(4096);
  const [llamacppTemperature, setLlamacppTemperature] = useState<number>(0.2);
  const [llamacppMaxTokens, setLlamacppMaxTokens] = useState<number>(2048);
  const [llamacppTest, setLlamacppTest] = useState<LlamaCppTest>({ state: "idle" });

  const checkLMStudio = async (url: string) => {
    setLmStudioTest({ state: "testing" });
    try {
      const data = await apiClient.settings.getLmStudioModels(url);
      if (data.online) {
        setLmStudioTest({ state: "online", models: data.models });
        if (data.models.length > 0) {
          setLmStudioModel((prev) => (!prev || !data.models.includes(prev) ? data.models[0] : prev));
        }
      } else {
        setLmStudioTest({ state: "offline", message: data.error ?? "LM Studio unreachable" });
      }
    } catch (e) {
      setLmStudioTest({ state: "offline", message: e instanceof Error ? e.message : "Unreachable" });
    }
  };

  const checkOllama = async (url: string) => {
    setOllamaTest({ state: "testing" });
    try {
      const data = await apiClient.settings.getOllamaModels(url);
      if (data.online) {
        setOllamaTest({ state: "online", models: data.models });
        if (data.models.length > 0) {
          setOllamaModel((prev) => (!prev || !data.models.includes(prev) ? data.models[0] : prev));
        }
      } else {
        setOllamaTest({ state: "offline", message: data.error ?? "Ollama unreachable" });
      }
    } catch (e) {
      setOllamaTest({ state: "offline", message: e instanceof Error ? e.message : "Unreachable" });
    }
  };

  const testLlamaCpp = async () => {
    setLlamacppTest({ state: "testing" });
    try {
      const health = await apiClient.settings.llamacppHealth(llamacppBaseUrl);
      if (!health.online) {
        setLlamacppTest({
          state: "offline",
          message: health.message ?? health.error ?? "llama.cpp local server is not running",
          endpoint: health.endpoint,
        });
        return;
      }
      const models = await apiClient.settings.llamacppModels(llamacppBaseUrl);
      setLlamacppTest({
        state: "online",
        latency_ms: health.latency_ms,
        endpoint: health.endpoint,
        models: models.models,
      });
    } catch (err) {
      setLlamacppTest({
        state: "offline",
        message: err instanceof Error ? err.message : "llama.cpp local server is not running",
      });
    }
  };

  const loadData = async () => {
    setLoadError(null);
    try {
      const [statusRes, settingsRes] = await Promise.all([
        apiClient.llm.status(),
        apiClient.settings.get(),
      ]);
      setStatus(statusRes);
      setSettings(settingsRes);

      setSelectedProvider(settingsRes.llm_provider);
      setLmStudioModel(settingsRes.lm_studio_model);
      setLmStudioBaseUrl(settingsRes.lm_studio_base_url);
      setOllamaBaseUrl(settingsRes.ollama_base_url);
      setOllamaModel(settingsRes.ollama_model);
      setLlamacppBaseUrl(settingsRes.llamacpp_base_url);
      setLlamacppModel(settingsRes.llamacpp_model);
      setLlamacppContextLength(settingsRes.llamacpp_context_length);
      setLlamacppTemperature(settingsRes.llamacpp_temperature);
      setLlamacppMaxTokens(settingsRes.llamacpp_max_tokens);

      if (statusRes.provider === "ollama") {
        checkOllama(settingsRes.ollama_base_url);
      } else {
        checkLMStudio(settingsRes.lm_studio_base_url);
      }

      // Non-blocking: persisted model/config preference is a nice-to-have
      // prefill, not required for the page to function.
      try {
        const me = await apiClient.workspaces.me();
        setWorkspaceId(me.id);
        const pref = await apiClient.workspaces.getProviderPreference(me.id);
        if (pref.provider && pref.model) {
          setProviderPreference(pref as ProviderPreference);
        }
      } catch (err) {
        console.error("Failed to load provider preference:", err);
      }
    } catch (err) {
      console.error(err);
      setLoadError(err instanceof Error ? err.message : "Failed to load settings.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload: Partial<SettingsUpdatePayload> = {
        llm_provider: selectedProvider,
        lm_studio_model: lmStudioModel,
        lm_studio_base_url: lmStudioBaseUrl,
        ollama_base_url: ollamaBaseUrl,
        ollama_model: ollamaModel,
        llamacpp_base_url: llamacppBaseUrl,
        llamacpp_model: llamacppModel,
        llamacpp_context_length: llamacppContextLength,
        llamacpp_temperature: llamacppTemperature,
        llamacpp_max_tokens: llamacppMaxTokens,
      };

      // Empty key field means "leave as-is" — never send a blank to clobber a saved/.env key.
      if (llamacppKey) payload.llamacpp_api_key = llamacppKey;

      const updated = await apiClient.settings.update(payload);
      setSettings(updated);

      const statusRes = await apiClient.llm.status();
      setStatus(statusRes);

      setLlamacppKey("");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to save settings";
      setLoadError(message);
    } finally {
      setSaving(false);
    }
  };

  // Derive local server display values for status card
  const activeProvider = status?.provider ?? selectedProvider;
  const isOllamaActive = activeProvider === "ollama";
  const isLmStudioActive = activeProvider === "lm_studio";
  const localTest = isOllamaActive ? ollamaTest : lmStudioTest;
  const localUrl = isOllamaActive ? ollamaBaseUrl : lmStudioBaseUrl;
  const localLabel = isOllamaActive ? "Ollama Host" : "LM Studio Host";
  const localModels = localTest.state === "online" ? localTest.models : [];
  const localOnline = localTest.state === "online";
  const localPinging = localTest.state === "testing";
  const showLocalCard = isOllamaActive || isLmStudioActive;

  const currentModelMap: Record<string, string> = {
    ollama: ollamaModel,
    lm_studio: lmStudioModel,
    llamacpp: llamacppModel,
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-4">
        <RefreshCw className="h-8 w-8 text-primary animate-spin" />
        <span className="text-muted-foreground text-sm">Loading pipeline configuration…</span>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <SettingsIcon className="h-6 w-6 text-primary" /> System Settings
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Configure active LLM extraction engines, endpoints, API keys, and model overrides.
        </p>
      </div>

      {loadError && (
        <div className="flex items-center justify-between gap-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          <span>{loadError}</span>
          <Button size="sm" variant="outline" onClick={loadData}>
            Retry
          </Button>
        </div>
      )}

      {/* Connection Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="border rounded-xl p-5 bg-card/65 backdrop-blur-md relative overflow-hidden group">
          <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-primary to-violet-500 opacity-60" />
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Active Engine</span>
            <Cpu className="h-4 w-4 text-primary" />
          </div>
          <div className="mt-3">
            <h3 className="text-xl font-bold capitalize">{status?.provider || "None"}</h3>
            <p className="text-xs text-muted-foreground truncate mt-1">{status?.model || "No model running"}</p>
          </div>
        </div>

        <div className="border rounded-xl p-5 bg-card/65 backdrop-blur-md relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-green-500 to-emerald-400 opacity-60" />
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              {showLocalCard ? localLabel : "Local Server"}
            </span>
            <Database className="h-4 w-4 text-emerald-500" />
          </div>
          <div className="mt-3 flex flex-col justify-between h-full">
            <div>
              <div className="flex items-center gap-1.5">
                <span className="text-xl font-bold">Local Server</span>
                {localPinging ? (
                  <Badge variant="outline" className="animate-pulse">Pinging</Badge>
                ) : showLocalCard && localOnline ? (
                  <Badge className="bg-green-500/10 text-green-500 border-green-500/20 text-[10px] py-0">Online</Badge>
                ) : showLocalCard ? (
                  <Badge className="bg-rose-500/10 text-rose-500 border-rose-500/20 text-[10px] py-0">Offline</Badge>
                ) : (
                  <Badge variant="secondary" className="text-[10px] py-0">Cloud</Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground truncate mt-1">{showLocalCard ? localUrl : (status?.endpoint ?? "—")}</p>
            </div>
          </div>
        </div>

        <div className="border rounded-xl p-5 bg-card/65 backdrop-blur-md relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-violet-500 to-indigo-500 opacity-60" />
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Loaded Models</span>
            <Badge variant="secondary" className="text-[10px]">{localModels.length} detected</Badge>
          </div>
          <div className="mt-3">
            {localModels.length > 0 ? (
              <span className="text-xl font-bold truncate block">{localModels[0]}</span>
            ) : (
              <span className="text-xl font-bold text-muted-foreground">
                {status?.model || "None"}
              </span>
            )}
            <p className="text-xs text-muted-foreground mt-1">Available for local JSON extraction</p>
          </div>
        </div>
      </div>

      {/* Cloud Providers — browser-session only (BYOK) */}
      <div className="space-y-3">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2">
            <CloudCog className="h-5 w-5 text-primary" /> Cloud Providers
          </h2>
          <p className="text-muted-foreground text-xs mt-1">
            Your API key stays in this browser tab&apos;s session only — never sent to or stored on our
            servers. It is cleared when this browser session ends. See{" "}
            <a href="/docs" className="underline underline-offset-2">
              the docs
            </a>{" "}
            for how to obtain a key.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {CLOUD_PROVIDERS.map((prov) => (
            <ProviderCard
              key={prov.id}
              provider={prov.id}
              label={prov.name}
              workspaceId={workspaceId}
              initialPreference={
                providerPreference?.provider === prov.id
                  ? { 
                      model: providerPreference.model, 
                      config: providerPreference.config,
                      has_saved_api_key: providerPreference.has_saved_api_key
                    }
                  : undefined
              }
            />
          ))}
        </div>
      </div>

      <form onSubmit={handleSave} className="space-y-6 border rounded-xl p-6 bg-card">
        <h2 className="text-lg font-bold">Local / Self-Hosted Pipeline Settings</h2>

        {/* Auto Detect */}
        <div className="space-y-2">
          <label className="text-sm font-medium">Provider Mode</label>
          <div
            onClick={() => setSelectedProvider("auto")}
            className={`border rounded-lg p-3 cursor-pointer transition-all flex items-center gap-2 ${
              selectedProvider === "auto" ? "border-primary bg-primary/5 ring-1 ring-primary" : "hover:bg-muted"
            }`}
          >
            <Sparkles className="h-4 w-4 text-primary shrink-0" />
            <div>
              <span className="text-sm font-semibold">Auto Detect</span>
              <p className="text-xs text-muted-foreground">
                Priority: browser session key → reachable LM Studio → Ollama → llama.cpp → admin .env cloud key.
              </p>
            </div>
          </div>
        </div>

        {/* Local Providers */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Local Providers</label>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {LOCAL_PROVIDERS.map((prov) => (
              <div
                key={prov.id}
                onClick={() => setSelectedProvider(prov.id)}
                className={`border rounded-lg p-3 cursor-pointer transition-all space-y-1 ${
                  selectedProvider === prov.id ? "border-primary bg-primary/5 ring-1 ring-primary" : "hover:bg-muted"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold">{prov.name}</span>
                  <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-500/20 text-[9px] py-0">
                    Local
                  </Badge>
                </div>
                <p className="text-[11px] text-muted-foreground truncate">
                  {currentModelMap[prov.id] || "No model set"}
                </p>
              </div>
            ))}
          </div>
        </div>

        <Tabs defaultValue="ollama" className="w-full pt-4">
          <TabsList className="grid grid-cols-3 w-full">
            <TabsTrigger value="ollama">Ollama</TabsTrigger>
            <TabsTrigger value="lm_studio">LM Studio</TabsTrigger>
            <TabsTrigger value="llamacpp">llama.cpp</TabsTrigger>
          </TabsList>

          {/* Ollama Tab */}
          <TabsContent value="ollama" className="space-y-4 pt-4 border-t">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-sm flex items-center gap-1.5">
                <Server className="h-4 w-4 text-emerald-500" /> Ollama (Local)
                <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-500/20 text-[10px] py-0 ml-1">
                  <ShieldCheck className="h-3 w-3 mr-1" /> Local Offline AI
                </Badge>
              </h3>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 gap-1.5"
                onClick={() => checkOllama(ollamaBaseUrl)}
                disabled={ollamaTest.state === "testing"}
              >
                <RefreshCw className={`h-3 w-3 ${ollamaTest.state === "testing" ? "animate-spin" : ""}`} />
                Test Connection
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">Ollama Host</label>
                <Input
                  value={ollamaBaseUrl}
                  onChange={(e) => setOllamaBaseUrl(e.target.value)}
                  placeholder="http://localhost:11434/v1"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">Model</label>
                {ollamaTest.state === "online" && ollamaTest.models.length > 0 ? (
                  <select
                    value={ollamaModel}
                    onChange={(e) => setOllamaModel(e.target.value)}
                    className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm ring-offset-background cursor-pointer focus:outline-none"
                  >
                    {ollamaTest.models.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                ) : (
                  <Input
                    value={ollamaModel}
                    onChange={(e) => setOllamaModel(e.target.value)}
                    placeholder="e.g. gemma3:4b"
                  />
                )}
              </div>
            </div>

            {ollamaTest.state === "online" && (
              <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4 text-xs">
                <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                <p className="text-emerald-600 font-semibold">
                  Connected — {ollamaTest.models.length} model(s) available
                </p>
              </div>
            )}

            {ollamaTest.state === "offline" && (
              <div className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50/50 p-4 text-xs text-red-700 dark:border-red-900/50 dark:bg-red-950/20 dark:text-red-400">
                <XCircle className="h-4 w-4 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold">Failed — {ollamaTest.message}</p>
                  <p className="mt-0.5 leading-relaxed">
                    Make sure Ollama is running: <code className="bg-muted/50 px-1 rounded">ollama serve</code>
                  </p>
                </div>
              </div>
            )}
          </TabsContent>

          {/* LM Studio Tab */}
          <TabsContent value="lm_studio" className="space-y-4 pt-4 border-t">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-sm">LM Studio (Local Host)</h3>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 gap-1.5"
                onClick={() => checkLMStudio(lmStudioBaseUrl)}
                disabled={lmStudioTest.state === "testing"}
              >
                <RefreshCw className={`h-3 w-3 ${lmStudioTest.state === "testing" ? "animate-spin" : ""}`} /> Test Connection
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">Endpoint</label>
                <Input
                  value={lmStudioBaseUrl}
                  onChange={(e) => setLmStudioBaseUrl(e.target.value)}
                  placeholder="http://localhost:1234/v1"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">Model</label>
                {lmStudioTest.state === "online" && lmStudioTest.models.length > 0 ? (
                  <select
                    value={lmStudioModel}
                    onChange={(e) => setLmStudioModel(e.target.value)}
                    className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm ring-offset-background cursor-pointer focus:outline-none"
                  >
                    {lmStudioTest.models.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                ) : (
                  <Input
                    value={lmStudioModel}
                    onChange={(e) => setLmStudioModel(e.target.value)}
                    placeholder="e.g. qwen/qwen3.5-9b"
                  />
                )}
              </div>
            </div>

            {lmStudioTest.state === "online" && (
              <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4 text-xs">
                <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                <p className="text-emerald-600 font-semibold">
                  Connected — {lmStudioTest.models.length} model(s) available
                </p>
              </div>
            )}

            {lmStudioTest.state === "offline" && (
              <div className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50/50 p-4 text-xs text-red-700 dark:border-red-900/50 dark:bg-red-950/20 dark:text-red-400">
                <XCircle className="h-4 w-4 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold">Failed — local LM Studio instance unreachable</p>
                  <p className="mt-0.5 leading-relaxed">
                    Make sure LM Studio is open, model is loaded, and &apos;Local Server&apos; is started on port 1234.
                  </p>
                </div>
              </div>
            )}
          </TabsContent>

          {/* llama.cpp Tab */}
          <TabsContent value="llamacpp" className="space-y-4 pt-4 border-t">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-sm flex items-center gap-1.5">
                <Server className="h-4 w-4 text-emerald-500" /> llama.cpp (Local Server)
                <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-500/20 text-[10px] py-0 ml-1">
                  <ShieldCheck className="h-3 w-3 mr-1" /> Local Offline AI
                </Badge>
              </h3>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 gap-1.5"
                onClick={testLlamaCpp}
                disabled={llamacppTest.state === "testing"}
              >
                <RefreshCw className={`h-3 w-3 ${llamacppTest.state === "testing" ? "animate-spin" : ""}`} />
                Test Connection
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">Endpoint</label>
                <Input
                  value={llamacppBaseUrl}
                  onChange={(e) => setLlamacppBaseUrl(e.target.value)}
                  placeholder="http://localhost:8080/v1"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">Model Name</label>
                <Input
                  value={llamacppModel}
                  onChange={(e) => setLlamacppModel(e.target.value)}
                  placeholder="local-model"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">API Key (optional)</label>
                <Input
                  type="password"
                  value={llamacppKey}
                  onChange={(e) => setLlamacppKey(e.target.value)}
                  placeholder={settings?.has_llamacpp_key ? "•••••••••••••••• (Saved)" : "not-needed (dummy ok)"}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">Context Length</label>
                <Input
                  type="number"
                  min={512}
                  step={256}
                  value={llamacppContextLength}
                  onChange={(e) => setLlamacppContextLength(Number(e.target.value))}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">Temperature</label>
                <Input
                  type="number"
                  min={0}
                  max={2}
                  step={0.05}
                  value={llamacppTemperature}
                  onChange={(e) => setLlamacppTemperature(Number(e.target.value))}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">Max Tokens</label>
                <Input
                  type="number"
                  min={64}
                  step={64}
                  value={llamacppMaxTokens}
                  onChange={(e) => setLlamacppMaxTokens(Number(e.target.value))}
                />
              </div>
            </div>

            {llamacppTest.state === "online" && (
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4 text-xs space-y-1">
                <p className="flex items-center gap-2 font-semibold text-emerald-600">
                  <CheckCircle2 className="h-4 w-4" /> Connected — latency {llamacppTest.latency_ms?.toFixed(0)}ms
                </p>
                {llamacppTest.models.length > 0 && (
                  <p className="text-muted-foreground">
                    Available models: {llamacppTest.models.join(", ")}
                  </p>
                )}
              </div>
            )}

            {llamacppTest.state === "offline" && (
              <div className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50/50 p-4 text-xs text-red-700 dark:border-red-900/50 dark:bg-red-950/20 dark:text-red-400">
                <XCircle className="h-4 w-4 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold">Failed — {llamacppTest.message}</p>
                  <p className="mt-0.5 leading-relaxed">
                    Start llama.cpp with: <code className="bg-muted/50 px-1 rounded">./llama-server -m model.gguf --port 8080</code>
                  </p>
                </div>
              </div>
            )}
          </TabsContent>
        </Tabs>

        <div className="flex justify-end gap-3 pt-4 border-t">
          <Button
            type="button"
            variant="ghost"
            onClick={() => loadData()}
            disabled={saving}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={saving}
            className="px-6"
          >
            {saving ? (
              <RefreshCw className="h-4 w-4 animate-spin mr-1.5" />
            ) : null}
            Save Settings & Reload Engine
          </Button>
        </div>
      </form>
    </div>
  );
}
