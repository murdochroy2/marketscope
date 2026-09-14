from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.api.deps import PortfolioServiceDep, SessionDep
from app.api.schemas import ErrorResponse, PortfolioUploadDetailOut, PortfolioUploadOut
from app.domain.errors import ValidationFailedError
from app.domain.portfolio_file import MAX_FILE_BYTES
from app.models import PortfolioUpload
from app.repositories.portfolio import PortfolioRepository

router = APIRouter(prefix="/portfolio-uploads", tags=["portfolio"])


def _detail(
    upload: PortfolioUpload, ignored_columns: list[str] | None = None
) -> PortfolioUploadDetailOut:
    return PortfolioUploadDetailOut(
        id=upload.id,
        filename=upload.filename,
        row_count=upload.row_count,
        rows_missing_coordinates=sum(1 for s in upload.stores if s.latitude is None),
        created_at=upload.created_at,
        ignored_columns=ignored_columns or [],
        stores=upload.stores,  # type: ignore[arg-type]
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=PortfolioUploadDetailOut,
    responses={422: {"model": ErrorResponse, "description": "Header or row validation failed"}},
)
async def upload_portfolio(service: PortfolioServiceDep, file: Annotated[UploadFile, File()]):
    # Read one byte past the limit so an oversized file is rejected without loading it all.
    content = await file.read(MAX_FILE_BYTES + 1)
    if not file.filename:
        raise ValidationFailedError("The uploaded file has no name")
    upload, ignored = await service.import_file(file.filename, content)
    return _detail(upload, ignored)


@router.get("", response_model=list[PortfolioUploadOut])
async def list_uploads(session: SessionDep):
    repo = PortfolioRepository(session)
    uploads = await repo.list_uploads()
    missing = await repo.missing_coordinate_counts([u.id for u in uploads])
    return [
        PortfolioUploadOut(
            id=u.id,
            filename=u.filename,
            row_count=u.row_count,
            rows_missing_coordinates=missing.get(u.id, 0),
            created_at=u.created_at,
        )
        for u in uploads
    ]


@router.get("/{upload_id}", response_model=PortfolioUploadDetailOut)
async def get_upload(upload_id: int, service: PortfolioServiceDep):
    return _detail(await service.get(upload_id))
