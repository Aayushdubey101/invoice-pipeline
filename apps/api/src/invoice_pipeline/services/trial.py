"""Phase 15 — free-trial gating for the platform's own .env LLM key.

A workspace (guest or authenticated) gets TRIAL_LIMIT calls against the
server's own LLM key before it must supply its own via BYOK (X-LLM-* headers
or a saved provider_preference — see llm/override.py). Only calls that use
the platform key are metered; a request carrying its own key never touches
this counter.
"""

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.db.models import Workspace

TRIAL_LIMIT = 5

TRIAL_EXHAUSTED_MESSAGE = (
    f"Free trial limit reached ({TRIAL_LIMIT}/{TRIAL_LIMIT} uses). "
    "Add your own LLM API key in Settings to continue."
)


async def consume_trial_use(workspace_id: str, session: AsyncSession) -> bool:
    """Atomically spend one trial credit. Returns False if none remain.

    The WHERE ... > 0 guard makes this race-safe under concurrent requests —
    two simultaneous calls can't both decrement past zero.
    """
    result = await session.execute(
        update(Workspace)
        .where(Workspace.id == workspace_id, Workspace.trial_uses_remaining > 0)
        .values(trial_uses_remaining=Workspace.trial_uses_remaining - 1)
    )
    await session.commit()
    return result.rowcount > 0
