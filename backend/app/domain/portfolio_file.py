"""Parsing and validation of uploaded portfolio (PF) files.

Policy: an upload is all-or-nothing. A portfolio is a snapshot of the business's own
estate, and a silently partial one would skew every inside/outside count downstream.
Instead of stopping at the first problem, validation collects every header and row error
so the user can fix the file in a single pass.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import PurePath

from openpyxl import load_workbook

REQUIRED_COLUMNS: tuple[str, ...] = (
    "store_name",
    "address",
    "city",
    "state",
    "country",
    "category",
)
OPTIONAL_COLUMNS: tuple[str, ...] = ("latitude", "longitude")
KNOWN_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

SUPPORTED_EXTENSIONS = (".csv", ".xlsx")
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
MAX_REPORTED_ROW_ERRORS = 200


@dataclass(frozen=True, slots=True)
class RowError:
    row: int  # 1-based spreadsheet row number, header included, so it matches what the user sees
    column: str | None
    message: str


@dataclass(frozen=True, slots=True)
class PortfolioRow:
    row_number: int
    store_name: str
    address: str
    city: str
    state: str
    country: str
    category: str
    latitude: float | None
    longitude: float | None

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None


@dataclass(slots=True)
class ValidationReport:
    missing_headers: list[str] = field(default_factory=list)
    duplicate_headers: list[str] = field(default_factory=list)
    unknown_headers: list[str] = field(default_factory=list)
    row_errors: list[RowError] = field(default_factory=list)
    file_errors: list[str] = field(default_factory=list)
    total_row_errors: int = 0

    @property
    def is_valid(self) -> bool:
        return not (
            self.missing_headers or self.duplicate_headers or self.row_errors or self.file_errors
        )

    def add_row_error(self, error: RowError) -> None:
        self.total_row_errors += 1
        if len(self.row_errors) < MAX_REPORTED_ROW_ERRORS:
            self.row_errors.append(error)


@dataclass(frozen=True, slots=True)
class ParsedPortfolio:
    rows: list[PortfolioRow]
    report: ValidationReport


def normalize_header(raw: object) -> str:
    return str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_table(filename: str, content: bytes) -> list[list[object]]:
    """Return the file as a list of raw rows. Raises ValueError for unreadable files."""
    extension = PurePath(filename).suffix.lower()
    if extension == ".csv":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("CSV must be UTF-8 encoded") from exc
        return [list(r) for r in csv.reader(io.StringIO(text))]
    if extension == ".xlsx":
        try:
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:  # openpyxl raises a zoo of exception types for bad files
            raise ValueError("file is not a readable .xlsx workbook") from exc
        sheet = workbook.worksheets[0]
        return [list(r) for r in sheet.iter_rows(values_only=True)]
    supported = ", ".join(SUPPORTED_EXTENSIONS)
    raise ValueError(f"unsupported file type '{extension or 'none'}'; upload one of {supported}")


def _parse_coordinate(
    raw: object, column: str, low: float, high: float, row_number: int, report: ValidationReport
) -> float | None:
    text = _cell_text(raw)
    if text == "":
        return None
    try:
        value = float(text)
    except ValueError:
        report.add_row_error(RowError(row_number, column, f"'{text}' is not a number"))
        return None
    if not low <= value <= high:
        report.add_row_error(
            RowError(row_number, column, f"{value} is outside the valid range {low:g} to {high:g}")
        )
        return None
    return value


def parse_portfolio(filename: str, content: bytes) -> ParsedPortfolio:
    report = ValidationReport()

    if len(content) > MAX_FILE_BYTES:
        report.file_errors.append(f"file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")
        return ParsedPortfolio([], report)

    try:
        table = read_table(filename, content)
    except ValueError as exc:
        report.file_errors.append(str(exc))
        return ParsedPortfolio([], report)

    # Keep each row's original 1-based position so errors point at the right line,
    # then drop fully blank rows, which spreadsheets are full of.
    numbered = [(n, r) for n, r in enumerate(table, start=1) if any(_cell_text(c) for c in r)]
    if not numbered:
        report.file_errors.append("file is empty")
        return ParsedPortfolio([], report)

    headers = [normalize_header(h) for h in numbered[0][1]]
    seen: set[str] = set()
    for h in headers:
        if h and h in seen and h not in report.duplicate_headers:
            report.duplicate_headers.append(h)
        seen.add(h)
    report.missing_headers = [c for c in REQUIRED_COLUMNS if c not in seen]
    report.unknown_headers = [h for h in headers if h and h not in KNOWN_COLUMNS]

    if report.missing_headers or report.duplicate_headers:
        # Row checks are meaningless without a trustworthy header.
        return ParsedPortfolio([], report)

    data_rows = numbered[1:]
    if not data_rows:
        report.file_errors.append("file has a header but no data rows")
        return ParsedPortfolio([], report)
    if len(data_rows) > MAX_ROWS:
        report.file_errors.append(f"file has {len(data_rows)} rows; the limit is {MAX_ROWS}")
        return ParsedPortfolio([], report)

    index = {h: i for i, h in enumerate(headers) if h}
    rows: list[PortfolioRow] = []

    for offset, raw in data_rows:

        def cell(column: str, raw_row: list[object] = raw) -> object:
            i = index.get(column)
            return raw_row[i] if i is not None and i < len(raw_row) else None

        errors_before = report.total_row_errors
        values: dict[str, str] = {}
        for column in REQUIRED_COLUMNS:
            text = _cell_text(cell(column))
            if not text:
                report.add_row_error(RowError(offset, column, "is required"))
            values[column] = text

        latitude = _parse_coordinate(cell("latitude"), "latitude", -90, 90, offset, report)
        longitude = _parse_coordinate(cell("longitude"), "longitude", -180, 180, offset, report)
        lat_given = _cell_text(cell("latitude")) != ""
        lng_given = _cell_text(cell("longitude")) != ""
        if lat_given != lng_given:
            missing = "longitude" if lat_given else "latitude"
            report.add_row_error(
                RowError(
                    offset,
                    missing,
                    "latitude and longitude must be given together or both left blank",
                )
            )

        if report.total_row_errors == errors_before:
            rows.append(
                PortfolioRow(
                    row_number=offset,
                    latitude=latitude,
                    longitude=longitude,
                    **values,
                )
            )

    return ParsedPortfolio(rows if report.is_valid else [], report)
