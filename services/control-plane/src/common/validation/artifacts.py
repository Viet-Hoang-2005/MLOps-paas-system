import csv
import io
from pathlib import Path
from typing import Any

from rest_framework.exceptions import ValidationError

MAX_SOURCE_CODE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_REFERENCE_DATA_BYTES = 100 * 1024 * 1024  # 100 MB


def validate_source_code_file(upload) -> str:
    """Validate that upload is a UTF-8 Python file under 5 MB."""
    name = Path(upload.name.replace("\\", "/")).name
    if not name.lower().endswith(".py") or len(name) > 255:
        raise ValidationError({"source_code_file": "Upload a Python (.py) file with a valid filename."})
    try:
        content = upload.read(MAX_SOURCE_CODE_BYTES + 1)
        if len(content) > MAX_SOURCE_CODE_BYTES:
            raise ValidationError(
                {"source_code_file": f"Source code file must be at most {MAX_SOURCE_CODE_BYTES // (1024 * 1024)} MiB."}
            )
        text = content.decode("utf-8")
        if "\x00" in text:
            raise ValidationError({"source_code_file": "Source code file cannot contain binary null bytes."})
        if not text.strip():
            raise ValidationError({"source_code_file": "Source code file cannot be empty."})
    except UnicodeDecodeError as exc:
        raise ValidationError({"source_code_file": "Source code file must be valid UTF-8 text."}) from exc
    finally:
        upload.seek(0)
    return name


def validate_reference_data_file(upload) -> tuple[str, str]:
    """Validate that upload is a CSV tabular dataset under 100 MB.

    Returns (filename, 'csv').
    """
    name = Path(upload.name.replace("\\", "/")).name
    suffix = Path(name).suffix.lower()
    if suffix != ".csv" or len(name) > 255:
        raise ValidationError({"reference_data_file": "Upload a CSV (.csv) file with a valid filename."})

    try:
        content = upload.read(MAX_REFERENCE_DATA_BYTES + 1)
        if len(content) > MAX_REFERENCE_DATA_BYTES:
            raise ValidationError(
                {
                    "reference_data_file": (
                        f"Reference data file must be at most {MAX_REFERENCE_DATA_BYTES // (1024 * 1024)} MiB."
                    )
                }
            )
        if len(content) == 0:
            raise ValidationError({"reference_data_file": "Reference data file cannot be empty."})

        try:
            text = content.decode("utf-8-sig")
            if "\x00" in text:
                raise ValidationError({"reference_data_file": "CSV file cannot contain binary null bytes."})
            rows = csv.reader(io.StringIO(text), strict=True)
            header = next(rows, None)
            if not header or any(not col.strip() for col in header) or len(set(header)) != len(header):
                raise ValidationError({"reference_data_file": "CSV must contain a header row with unique, non-empty column names."})
            count = 0
            for row in rows:
                if not row:
                    continue
                if len(row) != len(header):
                    raise ValidationError({"reference_data_file": "All CSV data rows must have the same number of columns as the header."})
                count += 1
            if count == 0:
                raise ValidationError({"reference_data_file": "CSV must contain at least one row of data."})
        except ValidationError:
            raise
        except (UnicodeDecodeError, csv.Error) as exc:
            raise ValidationError({"reference_data_file": f"Invalid CSV file format: {exc}"})
    except UnicodeDecodeError as exc:
        raise ValidationError({"reference_data_file": "CSV file must be valid UTF-8 text."}) from exc
    finally:
        upload.seek(0)

    return name, "csv"


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

