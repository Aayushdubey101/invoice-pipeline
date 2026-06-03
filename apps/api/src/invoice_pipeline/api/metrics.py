from prometheus_client import Counter, Histogram

UPLOADS_TOTAL = Counter("invoice_uploads_total", "Total invoice upload requests")
UPLOAD_ERRORS_TOTAL = Counter("invoice_upload_errors_total", "Total failed uploads")
PIPELINE_DURATION = Histogram(
    "invoice_pipeline_duration_seconds",
    "Pipeline processing duration",
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)
REVIEW_ACTIONS_TOTAL = Counter(
    "invoice_review_actions_total",
    "Review actions taken",
    labelnames=["action"],
)
