"""Phase 14: per-workspace upload directory.

Replaces the `Path(__file__).resolve().parents[4] / "data" / "uploads"`
computation duplicated across documents.py/batch.py with one workspace-scoped
helper, so a workspace's files live under their own subfolder and cleanup can
just delete that directory instead of matching files by Document id.
"""

from pathlib import Path

_UPLOAD_ROOT = Path(__file__).resolve().parents[3] / "data" / "uploads"


def upload_dir(workspace_id: str) -> Path:
    path = _UPLOAD_ROOT / workspace_id
    path.mkdir(parents=True, exist_ok=True)
    return path
