import { FileText } from "lucide-react";

export function Footer() {
  return (
    <footer className="w-full border-t border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto px-4 h-14 flex items-center justify-center gap-2 text-sm text-muted-foreground">
        <FileText className="h-4 w-4 text-primary" />
        <span>
          Developed by <span className="font-medium text-foreground">Aayush Dubey</span>
        </span>
      </div>
    </footer>
  );
}
