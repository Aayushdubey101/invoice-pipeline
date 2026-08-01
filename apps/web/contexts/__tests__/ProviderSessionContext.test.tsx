import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ProviderSessionProvider, useProviderSession } from "../ProviderSessionContext";

const STORAGE_KEY = "invoice_pipeline_provider_session";

function Consumer() {
  const { providers, activeProvider, setProviderConfig, clearProviderConfig, hasSessionProvider } =
    useProviderSession();
  return (
    <div>
      <span data-testid="has-provider">{String(hasSessionProvider())}</span>
      <span data-testid="active">{activeProvider ?? "none"}</span>
      <span data-testid="openai-key">{providers.openai?.apiKey ?? "unset"}</span>
      <button
        onClick={() =>
          setProviderConfig("openai", { apiKey: "sk-test-123", model: "gpt-4o-mini", config: {} })
        }
      >
        set
      </button>
      <button onClick={() => clearProviderConfig("openai")}>clear</button>
    </div>
  );
}

describe("ProviderSessionContext", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("persists a provider config to sessionStorage on set, and removes it on clear", async () => {
    render(
      <ProviderSessionProvider>
        <Consumer />
      </ProviderSessionProvider>
    );

    fireEvent.click(screen.getByText("set"));

    expect(await screen.findByTestId("openai-key")).toHaveTextContent("sk-test-123");

    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "{}");
    expect(stored.providers.openai.apiKey).toBe("sk-test-123");

    fireEvent.click(screen.getByText("clear"));

    expect(await screen.findByTestId("openai-key")).toHaveTextContent("unset");
    const storedAfterClear = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "{}");
    expect(storedAfterClear.providers.openai).toBeUndefined();
  });

  it("hydrates from an existing sessionStorage value on mount", async () => {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        providers: { anthropic: { apiKey: "sk-ant", model: "claude-sonnet-4-5", config: {} } },
        activeProvider: "anthropic",
      })
    );

    render(
      <ProviderSessionProvider>
        <Consumer />
      </ProviderSessionProvider>
    );

    expect(await screen.findByTestId("active")).toHaveTextContent("anthropic");
    expect(await screen.findByTestId("has-provider")).toHaveTextContent("true");
  });
});
