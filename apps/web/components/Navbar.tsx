"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Moon, Sun, FileText } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

const navLinks = [
  { href: "/", label: "Dashboard" },
  { href: "/upload", label: "Upload" },
  { href: "/review", label: "Review Queue" },
  { href: "/vendors", label: "Vendors" },
  { href: "/settings", label: "Settings" },
];

export function Navbar() {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();

  return (
    <header className="border-b bg-background/95 backdrop-blur sticky top-0 z-50">
      <div className="container mx-auto px-4 h-14 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2 font-semibold">
            <FileText className="h-5 w-5 text-primary" />
            <span>Invoice Intelligence</span>
          </Link>
          <Separator orientation="vertical" className="h-5" />
          <nav className="flex items-center gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "px-3 py-1.5 rounded-md text-sm transition-colors",
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
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label="Toggle theme"
        >
          <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
        </Button>
      </div>
    </header>
  );
}
