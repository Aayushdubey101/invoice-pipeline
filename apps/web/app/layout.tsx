import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Navbar } from "@/components/Navbar";
import { Providers } from "@/components/Providers";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Invoice Intelligence Pipeline",
  description: "Structured extraction from unstructured invoices with human-in-the-loop review",
  authors: [{ name: "Aayush Dubey", url: "https://github.com/Aayushdubey101" }],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.className} min-h-screen bg-background text-foreground antialiased`} suppressHydrationWarning>
        <Providers>
          <Navbar />
          <main className="container mx-auto px-4 py-8">{children}</main>
          <footer className="border-t py-6 mt-12">
            <div className="container mx-auto px-4 text-center text-sm text-muted-foreground">
              Built by{" "}
              <a
                href="https://github.com/Aayushdubey101"
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-foreground hover:text-primary transition-colors"
              >
                Aayush Dubey
              </a>
            </div>
          </footer>
        </Providers>
      </body>
    </html>
  );
}
