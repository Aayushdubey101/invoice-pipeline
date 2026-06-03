import { UploadDropzone } from "@/components/UploadDropzone";

export default function UploadPage() {
  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Upload Invoice</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Supports PDF, scanned images, and email files. Pipeline runs automatically.
        </p>
      </div>
      <UploadDropzone />
    </div>
  );
}
