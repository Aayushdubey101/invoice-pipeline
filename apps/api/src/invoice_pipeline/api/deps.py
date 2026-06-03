from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.db.session import get_session


async def db(session: AsyncSession = Depends(get_session)) -> AsyncGenerator[AsyncSession, None]:
    yield session
