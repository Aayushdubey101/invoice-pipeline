"use client";

import { useEffect, useState } from "react";
import {
  Cpu,
  Settings as SettingsIcon,
  Key,
  RefreshCw,
  AlertTriangle,
  Database,
  Server,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiClient, type AppSettings, type SettingsUpdatePayload } from "@/lib/api-client";

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

export default function SettingsPage() {
  const [status, setStatus] = useState<LLMStatus | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [selectedProvider, setSelectedProvider] = useState<string>("auto");

  // LM Studio
  const [lmStudioModel, setLmStudioModel] = useState<string>("");
  const [lmStudioBaseUrl, setLmStudioBaseUrl] = useState<string>("");
  const [lmStudioTest, setLmStudioTest] = useState<LocalServerTest>({ state: "idle" });

  // Ollama
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState<string>("");
  const [ollamaModel, setOllamaModel] = useState<string>("");
  const [ollamaTest, setOllamaTest] = useState<LocalServerTest>({ state: "idle" });

  // Cloud providers
  const [openaiKey, setOpenaiKey] = useState<string>("");
  const [openaiModel, setOpenaiModel] = useState<string>("");
  const [anthropicKey, setAnthropicKey] = useState<string>("");
  const [anthropicModel, setAnthropicModel] = useState<string>("");
  const [geminiKey, setGeminiKey] = useState<string>("");
  const [geminiModel, setGeminiModel] = useState<string>("");

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

  const loadData = async () => {
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
      setOpenaiModel(settingsRes.openai_model);
      setAnthropicModel(settingsRes.anthropic_model);
      setGeminiModel(settingsRes.gemini_model);
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
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
        openai_model: openaiModel,
        anthropic_model: anthropicModel,
        gemini_model: geminiModel,
        llamacpp_base_url: llamacppBaseUrl,
        llamacpp_model: llamacppModel,
        llamacpp_context_length: llamacppContextLength,
        llamacpp_temperature: llamacppTemperature,
        llamacpp_max_tokens: llamacppMaxTokens,
      };

      if (openaiKey) payload.openai_api_key = openaiKey;
      if (anthropicKey) payload.anthropic_api_key = anthropicKey;
      if (geminiKey) payload.gemini_api_key = geminiKey;
      if (llamacppKey) payload.llamacpp_api_key = llamacppKey;

      const updated = await apiClient.settings.update(payload);
      setSettings(updated);

      const statusRes = await apiClient.llm.status();
      setStatus(statusRes);

      setOpenaiKey("");
      setAnthropicKey("");
      setGeminiKey("");
      setLlamacppKey("");

      alert("Settings updated successfully and provider reloaded!");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to save settings";
      alert(message);
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
  const localModels =
    localTest.state === "online" ? localTest.models : [];
  const localOnline = localTest.state === "online";
  const localPinging = localTest.state === "testing";
  const showLocalCard = isOllamaActive || isLmStudioActive;

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

      <form onSubmit={handleSave} className="space-y-6 border rounded-xl p-6 bg-card">
        <h2 className="text-lg font-bold">LLM Pipeline Settings</h2>

        <div className="space-y-2">
          <label className="text-sm font-medium">Select LLM Provider</label>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { id: "auto", name: "Auto Detect" },
              { id: "ollama", name: "Ollama", badge: "Local Offline AI" },
              { id: "lm_studio", name: "LM Studio", badge: "Local Offline AI" },
              { id: "openai", name: "OpenAI API" },
              { id: "anthropic", name: "Anthropic" },
              { id: "gemini", name: "Google Gemini" },
              { id: "llamacpp", name: "llama.cpp", badge: "Local Offline AI" },
            ].map((prov) => (
              <div
                key={prov.id}
                onClick={() => setSelectedProvider(prov.id)}
                className={`border rounded-lg p-3 text-center cursor-pointer transition-all flex flex-col items-center gap-1 ${
                  selectedProvider === prov.id
                    ? "border-primary bg-primary/5 ring-1 ring-primary"
                    : "hover:bg-muted"
                }`}
              >
                <span className="text-xs font-semibold">{prov.name}</span>
                {prov.badge && (
                  <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-500/20 text-[9px] py-0">
                    {prov.badge}
                  </Badge>
                )}
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            Auto Detect prioritizes a reachable Ollama or LM Studio server, then falls back to configured API keys in order.
          </p>
        </div>

        <Tabs defaultValue="ollama" className="w-full pt-4">
          <TabsList className="grid grid-cols-6 w-full">
            <TabsTrigger value="ollama">Ollama</TabsTrigger>
            <TabsTrigger value="lm_studio">LM Studio</TabsTrigger>
            <TabsTrigger value="openai">OpenAI</TabsTrigger>
            <TabsTrigger value="anthropic">Anthropic</TabsTrigger>
            <TabsTrigger value="gemini">Gemini</TabsTrigger>
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
                Detect Models
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">Ollama Base URL</label>
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
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4 text-xs space-y-1">
                <p className="font-semibold text-emerald-600">
                  Connected — {ollamaTest.models.length} model(s) available
                </p>
                <p className="text-muted-foreground">Models: {ollamaTest.models.join(", ")}</p>
              </div>
            )}

            {ollamaTest.state === "offline" && (
              <div className="flex items-start gap-2.5 rounded-lg border border-yellow-200 bg-yellow-50/50 p-4 text-xs text-yellow-700 dark:border-yellow-900/50 dark:bg-yellow-950/20 dark:text-yellow-400">
                <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold">Ollama unreachable — {ollamaTest.message}</p>
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
                <RefreshCw className={`h-3 w-3 ${lmStudioTest.state === "testing" ? "animate-spin" : ""}`} /> Ping Local Server
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">Base Endpoint URL</label>
                <Input
                  value={lmStudioBaseUrl}
                  onChange={(e) => setLmStudioBaseUrl(e.target.value)}
                  placeholder="http://localhost:1234/v1"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">Active/Target Model</label>
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

            {lmStudioTest.state === "offline" && (
              <div className="flex items-start gap-2.5 rounded-lg border border-yellow-200 bg-yellow-50/50 p-4 text-xs text-yellow-700 dark:border-yellow-900/50 dark:bg-yellow-950/20 dark:text-yellow-400">
                <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold">Local LM Studio instance unreachable</p>
                  <p className="mt-0.5 leading-relaxed">
                    Make sure LM Studio is open, model is loaded, and &apos;Local Server&apos; is started on port 1234.
                  </p>
                </div>
              </div>
            )}
          </TabsContent>

          {/* OpenAI Tab */}
          <TabsContent value="openai" className="space-y-4 pt-4 border-t">
            <h3 className="font-semibold text-sm flex items-center gap-1.5">
              <Key className="h-4 w-4 text-amber-500" /> OpenAI Configuration
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">OpenAI Model</label>
                <Input
                  value={openaiModel}
                  onChange={(e) => setOpenaiModel(e.target.value)}
                  placeholder="gpt-4o-mini"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">API Key</label>
                <Input
                  type="password"
                  value={openaiKey}
                  onChange={(e) => setOpenaiKey(e.target.value)}
                  placeholder={settings?.has_openai_key ? "•••••••••••••••• (Saved)" : "Enter OpenAI API Key"}
                />
              </div>
            </div>
          </TabsContent>

          {/* Anthropic Tab */}
          <TabsContent value="anthropic" className="space-y-4 pt-4 border-t">
            <h3 className="font-semibold text-sm flex items-center gap-1.5">
              <Key className="h-4 w-4 text-amber-500" /> Anthropic Configuration
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">Anthropic Model</label>
                <Input
                  value={anthropicModel}
                  onChange={(e) => setAnthropicModel(e.target.value)}
                  placeholder="claude-3-5-sonnet"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">API Key</label>
                <Input
                  type="password"
                  value={anthropicKey}
                  onChange={(e) => setAnthropicKey(e.target.value)}
                  placeholder={settings?.has_anthropic_key ? "•••••••••••••••• (Saved)" : "Enter Anthropic API Key"}
                />
              </div>
            </div>
          </TabsContent>

          {/* Gemini Tab */}
          <TabsContent value="gemini" className="space-y-4 pt-4 border-t">
            <h3 className="font-semibold text-sm flex items-center gap-1.5">
              <Key className="h-4 w-4 text-amber-500" /> Gemini Configuration
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">Gemini Model</label>
                <Input
                  value={geminiModel}
                  onChange={(e) => setGeminiModel(e.target.value)}
                  placeholder="gemini-2.0-flash"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-semibold">API Key</label>
                <Input
                  type="password"
                  value={geminiKey}
                  onChange={(e) => setGeminiKey(e.target.value)}
                  placeholder={settings?.has_gemini_key ? "•••••••••••••••• (Saved)" : "Enter Gemini API Key"}
                />
              </div>
            </div>
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
                <label className="text-xs text-muted-foreground font-semibold">Base URL</label>
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
                <p className="font-semibold text-emerald-600">
                  Connected — latency {llamacppTest.latency_ms?.toFixed(0)}ms
                </p>
                <p className="text-muted-foreground">Endpoint: {llamacppTest.endpoint}</p>
                {llamacppTest.models.length > 0 && (
                  <p className="text-muted-foreground">
                    Available models: {llamacppTest.models.join(", ")}
                  </p>
                )}
              </div>
            )}

            {llamacppTest.state === "offline" && (
              <div className="flex items-start gap-2.5 rounded-lg border border-yellow-200 bg-yellow-50/50 p-4 text-xs text-yellow-700 dark:border-yellow-900/50 dark:bg-yellow-950/20 dark:text-yellow-400">
                <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold">{llamacppTest.message}</p>
                  <p className="mt-0.5 leading-relaxed">
                    Start llama.cpp with: <code className="bg-muted/50 px-1 rounded">./llama-server -m model.gguf --port 8080</code>
                  </p>
                </div>
              </div>
            )}

            <p className="text-[11px] text-muted-foreground leading-relaxed">
              Compatible with llama.cpp, LM Studio, and Ollama OpenAI-compatible endpoints. JSON-schema first,
              markdown-fenced JSON fallback. Streaming supported.
            </p>
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
