import { render, screen } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { Navbar } from "../Navbar";
import { useWorkspaceSession } from "@/contexts/WorkspaceSessionContext";
import { ProviderSessionProvider } from "@/contexts/ProviderSessionContext";
import { ThemeProvider } from "next-themes";
import * as clerkNextjs from "@clerk/nextjs";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn() }),
}));

// Mock WorkspaceSessionContext
vi.mock("@/contexts/WorkspaceSessionContext", () => ({
  useWorkspaceSession: vi.fn(),
}));

// Mock next-themes
vi.mock("next-themes", () => ({
  useTheme: () => ({ theme: "light", setTheme: vi.fn() }),
  ThemeProvider: ({ children }: any) => <>{children}</>,
}));

// Mock Clerk components
vi.mock("@clerk/nextjs", () => {
  return {
    SignedIn: ({ children }: any) => {
      const { isSignedIn } = clerkNextjs.useAuth();
      return isSignedIn ? <>{children}</> : null;
    },
    SignedOut: ({ children }: any) => {
      const { isSignedIn } = clerkNextjs.useAuth();
      return !isSignedIn ? <>{children}</> : null;
    },
    UserButton: () => <button data-testid="clerk-user-button">User Button</button>,
    useAuth: vi.fn(),
    useUser: vi.fn(),
  };
});

describe("Navbar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Default workspace mock (no active workspace)
    vi.mocked(useWorkspaceSession).mockReturnValue({
      hasActiveWorkspace: () => false,
      expiresAt: null,
      createWorkspace: vi.fn(),
    } as any);
  });

  const renderNavbar = () => {
    return render(
      <ThemeProvider>
        <ProviderSessionProvider>
          <Navbar />
        </ProviderSessionProvider>
      </ThemeProvider>
    );
  };

  it("renders correctly when signed out with NO guest workspace", () => {
    vi.mocked(clerkNextjs.useAuth).mockReturnValue({ isSignedIn: false } as any);
    
    renderNavbar();
    
    // Brand should be there
    expect(screen.getByText("Invoice Intelligence")).toBeInTheDocument();
    
    // UserButton should NOT be there
    expect(screen.queryByTestId("clerk-user-button")).not.toBeInTheDocument();
    
    // Guest badge should NOT be there
    expect(screen.queryByText(/Guest/)).not.toBeInTheDocument();
  });

  it("renders guest badge when signed out with an active guest workspace", () => {
    vi.mocked(clerkNextjs.useAuth).mockReturnValue({ isSignedIn: false } as any);
    
    // Mock active guest workspace
    vi.mocked(useWorkspaceSession).mockReturnValue({
      hasActiveWorkspace: () => true,
      expiresAt: new Date(Date.now() + 3600 * 1000).toISOString(),
      createWorkspace: vi.fn(),
    } as any);
    
    renderNavbar();
    
    // UserButton should NOT be there
    expect(screen.queryByTestId("clerk-user-button")).not.toBeInTheDocument();
    
    // Guest badge and Finish Session button SHOULD be there
    expect(screen.getByText(/Guest/)).toBeInTheDocument();
    expect(screen.getByText(/Finish Session/)).toBeInTheDocument();
  });

  it("renders UserButton when signed in and hides guest badge even if active workspace exists (mutually exclusive state edge case handled by SignedOut)", () => {
    vi.mocked(clerkNextjs.useAuth).mockReturnValue({ isSignedIn: true } as any);
    
    // Even if context says there is an active workspace, the SignedOut block prevents it
    vi.mocked(useWorkspaceSession).mockReturnValue({
      hasActiveWorkspace: () => true,
      expiresAt: new Date().toISOString(),
      createWorkspace: vi.fn(),
    } as any);
    
    renderNavbar();
    
    // UserButton SHOULD be there
    expect(screen.getByTestId("clerk-user-button")).toBeInTheDocument();
    
    // Guest badge should NOT be there
    expect(screen.queryByText(/Guest/)).not.toBeInTheDocument();
  });
});
