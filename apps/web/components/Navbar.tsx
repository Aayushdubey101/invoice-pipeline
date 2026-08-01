"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Moon, Sun, FileText, LogOut, Menu } from "lucide-react";
import { useTheme } from "next-themes";
import { UserButton, useAuth } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { useWorkspaceSession } from "@/contexts/WorkspaceSessionContext";
import { FinishSessionDialog } from "@/components/FinishSessionDialog";

const navLinks = [
  { href: "/", label: "Home" },
  { href: "/upload", label: "Upload" },
  { href: "/review", label: "Review Queue" },
  { href: "/batches", label: "Batches" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/vendors", label: "Vendors" },
  { href: "/settings", label: "Settings" },
  { href: "/docs", label: "Docs" },
];

export function Navbar() {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const { hasActiveWorkspace, expiresAt } = useWorkspaceSession();
  const { isSignedIn } = useAuth();
  const [finishOpen, setFinishOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const guestBadge = !isSignedIn && hasActiveWorkspace() && (
    <>
      <Badge variant="secondary">
        Guest
        {expiresAt
          ? ` · expires ${new Date(expiresAt).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}`
          : ""}
      </Badge>
      <Button
        variant="outline"
        size="sm"
        className="gap-1.5"
        onClick={() => setFinishOpen(true)}
      >
        <LogOut className="h-3.5 w-3.5" /> Finish Session
      </Button>
      <FinishSessionDialog open={finishOpen} onOpenChange={setFinishOpen} />
    </>
  );

  const themeToggle = (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      aria-label="Toggle theme"
    >
      <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
      <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
    </Button>
  );

  return (
    <nav className="fixed top-0 w-full z-50 border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto px-4 h-14 flex items-center justify-between gap-2">
        <div className="flex items-center gap-4 md:gap-6 min-w-0">
          <Link href="/" className="flex items-center gap-2 font-semibold shrink-0">
            <FileText className="h-5 w-5 text-primary" />
            <span className="hidden sm:inline">Invoice Intelligence</span>
          </Link>
          <Separator orientation="vertical" className="h-5 hidden md:block" />
          <nav className="hidden md:flex items-center gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "px-3 py-1.5 rounded-md text-sm transition-colors whitespace-nowrap",
                  pathname === link.href
                    ? "bg-primary/10 text-primary font-medium"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted"
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2 md:gap-3">
          <div className="hidden md:flex items-center gap-3">
            {guestBadge}
          </div>
          {isSignedIn && <UserButton />}
          {themeToggle}
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger className="md:hidden" render={
              <Button variant="ghost" size="icon" aria-label="Open menu">
                <Menu className="h-5 w-5" />
              </Button>
            } />
            <SheetContent side="right" className="w-72 flex flex-col gap-1 p-4">
              <SheetTitle>Menu</SheetTitle>
              <nav className="flex flex-col gap-1 mt-2">
                {navLinks.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    onClick={() => setMobileOpen(false)}
                    className={cn(
                      "px-3 py-2 rounded-md text-sm transition-colors",
                      pathname === link.href
                        ? "bg-primary/10 text-primary font-medium"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted"
                    )}
                  >
                    {link.label}
                  </Link>
                ))}
              </nav>
              {guestBadge && (
                <div className="flex flex-col items-start gap-2 mt-4 pt-4 border-t border-border">
                  {guestBadge}
                </div>
              )}
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </nav>
  );
}
