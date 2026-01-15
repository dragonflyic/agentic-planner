"""API dependency injection."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.db.session import get_db

# Type alias for database session dependency
DbSession = Annotated[AsyncSession, Depends(get_db)]
