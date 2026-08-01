import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";
import { Providers } from "@/components/Providers";
import { ClerkProvider } from "@clerk/nextjs";


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
      <body className={`${inter.className} min-h-screen flex flex-col bg-background text-foreground antialiased`} suppressHydrationWarning>
        <ClerkProvider>
          <Providers>
            <Navbar />
            <main className="container mx-auto px-4 pt-20 pb-8 flex-1">{children}</main>
            <Footer />
          </Providers>
        </ClerkProvider>
      </body>
    </html>
  );
}
