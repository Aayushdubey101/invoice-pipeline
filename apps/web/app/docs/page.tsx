import type { Metadata } from "next";
import { ShieldCheck, KeyRound, UploadCloud, Settings2, HelpCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Docs — Invoice Intelligence Pipeline",
  description: "How to configure an AI provider and use the invoice pipeline.",
};

const PROVIDER_KEY_LINKS = [
  { name: "OpenAI", url: "https://platform.openai.com/api-keys" },
  { name: "Anthropic", url: "https://console.anthropic.com/settings/keys" },
  { name: "Google Gemini", url: "https://aistudio.google.com/apikey" },
  { name: "Groq", url: "https://console.groq.com/keys" },
];

const FAQ_ITEMS = [
  {
    q: "\"Invalid API key\"",
    a: "The key was rejected by the provider. Double-check you copied the full key with no leading/trailing spaces, and that it hasn't been revoked or rotated in the provider's console.",
  },
  {
    q: "\"Model not found\"",
    a: "The model name doesn't exist or isn't available to your account/tier. Check the exact model identifier in the provider's model list.",
  },
  {
    q: "\"Quota exceeded\"",
    a: "Your account has hit its usage/billing limit with the provider. Check your usage dashboard and billing status on the provider's site.",
  },
  {
    q: "\"Network timeout\"",
    a: "The provider didn't respond in time. Usually transient — retry. If it persists, check the provider's status page.",
  },
  {
    q: "\"Rate limited\"",
    a: "Too many requests in a short window. Wait a moment and try again, or reduce concurrent uploads.",
  },
];

// ponytail: no screenshots — text-only walkthrough for now, add screenshots if users ask.
export default function DocsPage() {
  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Documentation</h1>
        <p className="text-muted-foreground text-sm mt-1">
          How to configure an AI provider and process invoices with this platform.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <UploadCloud className="h-5 w-5 text-primary" /> Getting Started
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="list-decimal list-inside space-y-2 text-sm">
            <li>Go to <span className="font-medium">Settings</span> and pick a cloud provider card (OpenAI, Anthropic, Gemini, or Groq).</li>
            <li>Enter a model name and your API key for that provider.</li>
            <li>Click <span className="font-medium">Test Connection</span> to verify the key works.</li>
            <li>Once the test succeeds, click <span className="font-medium">Save For This Session</span>.</li>
            <li>Go to <span className="font-medium">Upload</span> and drop in one or more invoices (PDF, PNG, JPEG, TIFF).</li>
            <li>Review extracted fields on the <span className="font-medium">Review Queue</span> and approve or correct them.</li>
            <li>Export approved invoices to Excel from the dashboard.</li>
          </ol>
          <p className="text-xs text-muted-foreground mt-3">
            Alternatively, if a local provider (Ollama, LM Studio, llama.cpp) is running and configured by
            the site operator, or the operator has set an admin fallback key, uploads work without
            configuring a browser session key.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-primary" /> Supported Providers &amp; API Keys
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm">
            {PROVIDER_KEY_LINKS.map((p) => (
              <li key={p.name} className="flex items-center justify-between gap-4">
                <span className="font-medium">{p.name}</span>
                <a href={p.url} target="_blank" rel="noreferrer" className="text-primary underline underline-offset-2 text-xs break-all">
                  {p.url}
                </a>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings2 className="h-5 w-5 text-primary" /> Configuring Model, API Key &amp; JSON Config
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            <span className="font-medium text-foreground">Model</span> — the provider&apos;s model identifier,
            e.g. <code className="bg-muted px-1 rounded">gpt-4o-mini</code>,{" "}
            <code className="bg-muted px-1 rounded">claude-sonnet-4-5</code>,{" "}
            <code className="bg-muted px-1 rounded">gemini-2.0-flash</code>, or{" "}
            <code className="bg-muted px-1 rounded">llama-3.3-70b-versatile</code>.
          </p>
          <p>
            <span className="font-medium text-foreground">API Key</span> — pasted directly into the
            provider card; toggle the eye icon to confirm what you typed.
          </p>
          <p>
            <span className="font-medium text-foreground">JSON Config</span> (optional) — extra
            provider-specific parameters, e.g. <code className="bg-muted px-1 rounded">{`{"temperature": 0.2}`}</code>.
            Must be a valid JSON object; invalid JSON is flagged inline and blocks Test Connection.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-emerald-500" /> Security Notice
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm">Your API key</p>
          <ul className="mt-1 space-y-1 text-sm">
            <li>✓ never leaves your browser except for requests made to the selected provider</li>
            <li>✓ is never stored on our servers</li>
            <li>✓ is removed when your browser session ends</li>
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HelpCircle className="h-5 w-5 text-primary" /> FAQ / Troubleshooting
          </CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="space-y-3 text-sm">
            {FAQ_ITEMS.map((item) => (
              <div key={item.q}>
                <dt className="font-medium">{item.q}</dt>
                <dd className="text-muted-foreground">{item.a}</dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}
