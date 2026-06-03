import { ReviewQueue } from "@/components/ReviewQueue";

export default function ReviewPage() {
  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Review Queue</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Invoices with low-confidence fields or unresolved vendors awaiting human review.
        </p>
      </div>
      <ReviewQueue />
    </div>
  );
}
