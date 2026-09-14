import io

from openpyxl import Workbook

from app.domain.portfolio_file import MAX_FILE_BYTES, parse_portfolio

HEADER = "store_name,address,city,state,country,category,latitude,longitude"


def csv(*lines: str) -> bytes:
    return "\n".join(lines).encode()


def test_sample_file_is_valid(sample_csv_bytes):
    parsed = parse_portfolio("sample.csv", sample_csv_bytes)
    assert parsed.report.is_valid
    assert len(parsed.rows) == 10
    missing = [r.store_name for r in parsed.rows if not r.has_coordinates]
    assert missing == [
        "BigBasket Hyperstore Whitefield",
        "More Supermarket JP Nagar",
        "Wellness Forever Pharmacy Rajajinagar",
    ]


def test_missing_required_headers_are_all_listed_and_no_rows_parsed():
    parsed = parse_portfolio("p.csv", csv("store_name,city,latitude", "A,Bengaluru,12.9"))
    assert parsed.report.missing_headers == ["address", "state", "country", "category"]
    assert parsed.rows == []
    assert not parsed.report.row_errors


def test_coordinate_columns_are_optional():
    parsed = parse_portfolio(
        "p.csv",
        csv("store_name,address,city,state,country,category", "A,1 Rd,Bengaluru,KA,India,Pharmacy"),
    )
    assert parsed.report.is_valid
    assert parsed.rows[0].latitude is None


def test_headers_are_normalised():
    parsed = parse_portfolio(
        "p.csv",
        csv(
            " Store Name ,ADDRESS,City,State,Country,Category", "A,1 Rd,Bengaluru,KA,India,Pharmacy"
        ),
    )
    assert parsed.report.is_valid


def test_duplicate_headers_are_rejected():
    parsed = parse_portfolio("p.csv", csv(HEADER + ",city", "A,1 Rd,B,KA,IN,Pharmacy,,,"))
    assert parsed.report.duplicate_headers == ["city"]
    assert not parsed.report.is_valid


def test_unknown_headers_are_reported_but_allowed():
    parsed = parse_portfolio("p.csv", csv(HEADER + ",manager", "A,1 Rd,B,KA,IN,Pharmacy,,,Ravi"))
    assert parsed.report.is_valid
    assert parsed.report.unknown_headers == ["manager"]


def test_row_errors_carry_spreadsheet_row_numbers_and_reject_the_file():
    parsed = parse_portfolio(
        "p.csv",
        csv(
            HEADER,
            "Good,1 Rd,B,KA,IN,Pharmacy,12.9,77.6",
            "BadLat,1 Rd,B,KA,IN,Pharmacy,abc,77.6",
            "",  # blank lines are skipped but still count toward row numbers
            "OutOfRange,1 Rd,B,KA,IN,Pharmacy,95,77.6",
            "HalfCoord,1 Rd,B,KA,IN,Pharmacy,12.9,",
            ",1 Rd,B,KA,IN,Pharmacy,,",
        ),
    )
    errors = {(e.row, e.column) for e in parsed.report.row_errors}
    assert errors == {
        (3, "latitude"),
        (5, "latitude"),
        (6, "longitude"),
        (7, "store_name"),
    }
    assert parsed.rows == []  # all-or-nothing


def test_xlsx_numbers_and_blank_cells_parse_like_csv():
    wb = Workbook()
    ws = wb.active
    ws.append(HEADER.split(","))
    ws.append(["A", "1 Rd", "Bengaluru", "KA", "India", "Pharmacy", 12.93, 77.62])
    ws.append(["B", "2 Rd", "Bengaluru", "KA", "India", "Pharmacy", None, None])
    buf = io.BytesIO()
    wb.save(buf)
    parsed = parse_portfolio("p.xlsx", buf.getvalue())
    assert parsed.report.is_valid
    assert [r.latitude for r in parsed.rows] == [12.93, None]


def test_unsupported_extension_and_corrupt_xlsx():
    assert parse_portfolio("p.txt", b"x").report.file_errors
    assert parse_portfolio("p.xlsx", b"not a zip").report.file_errors


def test_empty_and_header_only_files():
    assert parse_portfolio("p.csv", b"").report.file_errors == ["file is empty"]
    assert parse_portfolio("p.csv", csv(HEADER)).report.file_errors == [
        "file has a header but no data rows"
    ]


def test_oversized_file_is_rejected_before_parsing():
    parsed = parse_portfolio("p.csv", b"x" * (MAX_FILE_BYTES + 1))
    assert parsed.report.file_errors
