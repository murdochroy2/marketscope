from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import NotFoundError, ValidationFailedError
from app.domain.portfolio_file import ValidationReport, parse_portfolio
from app.models import GeocodeStatus, PortfolioStore, PortfolioUpload
from app.repositories.portfolio import PortfolioRepository


def report_details(report: ValidationReport) -> dict:
    return {
        "file_errors": report.file_errors,
        "missing_headers": report.missing_headers,
        "duplicate_headers": report.duplicate_headers,
        "unknown_headers": report.unknown_headers,
        "row_errors": [
            {"row": e.row, "column": e.column, "message": e.message} for e in report.row_errors
        ],
        "total_row_errors": report.total_row_errors,
    }


def summarize_failure(report: ValidationReport) -> str:
    if report.file_errors:
        return report.file_errors[0].capitalize()
    if report.missing_headers:
        return f"Missing required columns: {', '.join(report.missing_headers)}"
    if report.duplicate_headers:
        return f"Duplicate columns: {', '.join(report.duplicate_headers)}"
    rows = len({e.row for e in report.row_errors})
    total = report.total_row_errors
    problems = "1 problem" if total == 1 else f"{total} problems"
    where = "1 row" if rows == 1 else f"{rows} rows"
    if total > len(report.row_errors):
        where = f"at least {where}"
    return f"Found {problems} in {where}. Nothing was imported."


class PortfolioService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = PortfolioRepository(session)

    async def import_file(self, filename: str, content: bytes) -> tuple[PortfolioUpload, list[str]]:
        parsed = parse_portfolio(filename, content)
        if not parsed.report.is_valid:
            raise ValidationFailedError(
                summarize_failure(parsed.report), report_details(parsed.report)
            )

        upload = PortfolioUpload(filename=filename, row_count=len(parsed.rows))
        upload.stores = [
            PortfolioStore(
                row_number=row.row_number,
                store_name=row.store_name,
                address=row.address,
                city=row.city,
                state=row.state,
                country=row.country,
                category=row.category,
                latitude=row.latitude,
                longitude=row.longitude,
                geocode_status=GeocodeStatus.NOT_NEEDED
                if row.has_coordinates
                else GeocodeStatus.PENDING,
            )
            for row in parsed.rows
        ]
        self._repo.add_upload(upload)
        await self._session.commit()
        return upload, parsed.report.unknown_headers

    async def get(self, upload_id: int) -> PortfolioUpload:
        upload = await self._repo.get_upload(upload_id, with_stores=True)
        if upload is None:
            raise NotFoundError(f"Portfolio upload {upload_id} does not exist")
        return upload
