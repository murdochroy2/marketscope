from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import PortfolioStore, PortfolioUpload


class PortfolioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_upload(self, upload: PortfolioUpload) -> None:
        self._session.add(upload)

    async def get_upload(
        self, upload_id: int, *, with_stores: bool = False
    ) -> PortfolioUpload | None:
        stmt = select(PortfolioUpload).where(PortfolioUpload.id == upload_id)
        if with_stores:
            stmt = stmt.options(selectinload(PortfolioUpload.stores))
        return await self._session.scalar(stmt)

    async def list_uploads(self, limit: int = 20) -> Sequence[PortfolioUpload]:
        stmt = select(PortfolioUpload).order_by(PortfolioUpload.id.desc()).limit(limit)
        return (await self._session.scalars(stmt)).all()

    async def stores_for_upload(self, upload_id: int) -> Sequence[PortfolioStore]:
        stmt = (
            select(PortfolioStore)
            .where(PortfolioStore.upload_id == upload_id)
            .order_by(PortfolioStore.row_number)
        )
        return (await self._session.scalars(stmt)).all()

    async def missing_coordinate_counts(self, upload_ids: Sequence[int]) -> dict[int, int]:
        if not upload_ids:
            return {}
        stmt = (
            select(PortfolioStore.upload_id, func.count())
            .where(PortfolioStore.upload_id.in_(upload_ids), PortfolioStore.latitude.is_(None))
            .group_by(PortfolioStore.upload_id)
        )
        return {uid: n for uid, n in (await self._session.execute(stmt)).all()}
