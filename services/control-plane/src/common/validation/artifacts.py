import csv
import io
from pathlib import Path
from typing import Any

from rest_framework.exceptions import ValidationError

MAX_SOURCE_CODE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_REFERENCE_DATA_BYTES = 100 * 1024 * 1024  # 100 MB


def validate_source_code_content(name: str, content: bytes, error_key: str = "source_code") -> str:
    """Validate that content is valid UTF-8 Python text under 5 MB."""
    filename = Path(name.replace("\\", "/")).name
    if not filename.lower().endswith(".py") or len(filename) > 255:
        raise ValidationError({error_key: "Upload a Python (.py) file with a valid filename."})
    if len(content) > MAX_SOURCE_CODE_BYTES:
        raise ValidationError(
            {error_key: f"Source code file must be at most {MAX_SOURCE_CODE_BYTES // (1024 * 1024)} MiB."}
        )
    if len(content) == 0:
        raise ValidationError({error_key: "Source code file cannot be empty."})
    try:
        text = content.decode("utf-8")
        if "\x00" in text:
            raise ValidationError({error_key: "Source code file cannot contain binary null bytes."})
        if not text.strip():
            raise ValidationError({error_key: "Source code file cannot be empty."})
    except UnicodeDecodeError as exc:
        raise ValidationError({error_key: "Source code file must be valid UTF-8 text."}) from exc
    return filename


def validate_source_code_file(upload) -> str:
    """Validate that upload is a UTF-8 Python file under 5 MB."""
    name = Path(getattr(upload, "name", "source_code.py").replace("\\", "/")).name
    try:
        content = upload.read(MAX_SOURCE_CODE_BYTES + 1)
        return validate_source_code_content(name, content, error_key="source_code_file")
    finally:
        upload.seek(0)


def validate_reference_data_content(name: str, content: bytes, error_key: str = "reference_data") -> tuple[str, str]:
    """Validate that content is a valid UTF-8 CSV tabular dataset under 100 MB.

    Returns (filename, 'csv').
    """
    filename = Path(name.replace("\\", "/")).name
    suffix = Path(filename).suffix.lower()
    if suffix != ".csv" or len(filename) > 255:
        raise ValidationError({error_key: "Upload a CSV (.csv) file with a valid filename."})

    if len(content) > MAX_REFERENCE_DATA_BYTES:
        raise ValidationError(
            {error_key: f"Reference data file must be at most {MAX_REFERENCE_DATA_BYTES // (1024 * 1024)} MiB."}
        )
    if len(content) == 0:
        raise ValidationError({error_key: "Reference data file cannot be empty."})

    try:
        text = content.decode("utf-8-sig")
        if "\x00" in text:
            raise ValidationError({error_key: "CSV file cannot contain binary null bytes."})
        rows = csv.reader(io.StringIO(text), strict=True)
        header = next(rows, None)
        if not header or any(not col.strip() for col in header) or len(set(header)) != len(header):
            raise ValidationError({error_key: "CSV must contain a header row with unique, non-empty column names."})
        count = 0
        for row in rows:
            if not row:
                continue
            if len(row) != len(header):
                raise ValidationError({error_key: "All CSV data rows must have the same number of columns as the header."})
            count += 1
        if count == 0:
            raise ValidationError({error_key: "CSV must contain at least one row of data."})
    except ValidationError:
        raise
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValidationError({error_key: f"Invalid CSV file format: {exc}"})

    return filename, "csv"


def validate_reference_data_file(upload) -> tuple[str, str]:
    """Validate that upload is a CSV tabular dataset under 100 MB.

    Returns (filename, 'csv').
    """
    name = Path(getattr(upload, "name", "reference_data.csv").replace("\\", "/")).name
    try:
        content = upload.read(MAX_REFERENCE_DATA_BYTES + 1)
        return validate_reference_data_content(name, content, error_key="reference_data_file")
    finally:
        upload.seek(0)


def parse_reference_preview(data_bytes: bytes, filename: str, max_rows: int = 100) -> dict[str, Any]:
    """Extract schema and first max_rows rows from CSV bytes."""
    text = data_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    header = next(reader, [])
    rows = []
    total_rows = 0
    for row in reader:
        if not row:
            continue
        total_rows += 1
        if len(rows) < max_rows:
            rows.append(row)
    return {
        "filename": filename,
        "format": "csv",
        "columns": header,
        "rows": rows,
        "total_rows": total_rows,
    }

