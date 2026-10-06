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
    """Validate that upload is a CSV or Parquet tabular dataset under 100 MB.

    Returns (filename, format) where format is 'csv' or 'parquet'.
    """
    name = Path(upload.name.replace("\\", "/")).name
    suffix = Path(name).suffix.lower()
    if suffix not in {".csv", ".parquet"} or len(name) > 255:
        raise ValidationError({"reference_data_file": "Upload a CSV (.csv) or Parquet (.parquet) file with a valid filename."})

    fmt = "csv" if suffix == ".csv" else "parquet"
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

        if fmt == "csv":
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
        else:
            # Parquet validation using pyarrow
            import pyarrow.parquet as pq

            try:
                pf = pq.ParquetFile(io.BytesIO(content))
                schema = pf.schema_arrow
                columns = schema.names
                if not columns or any(not col.strip() for col in columns) or len(set(columns)) != len(columns):
                    raise ValidationError({"reference_data_file": "Parquet file must contain unique, non-empty column names."})
                if pf.metadata.num_rows <= 0:
                    raise ValidationError({"reference_data_file": "Parquet file must contain at least one row of data."})
            except ValidationError:
                raise
            except Exception as exc:
                raise ValidationError({"reference_data_file": f"Invalid Parquet file: {exc}"}) from exc

    except UnicodeDecodeError as exc:
        raise ValidationError({"reference_data_file": "CSV file must be valid UTF-8 text."}) from exc
    finally:
        upload.seek(0)

    return name, fmt


def parse_reference_preview(data_bytes: bytes, filename: str, max_rows: int = 100) -> dict[str, Any]:
    """Extract schema and first max_rows rows from CSV or Parquet bytes."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".parquet":
        import pyarrow.parquet as pq

        pf = pq.ParquetFile(io.BytesIO(data_bytes))
        columns = pf.schema_arrow.names
        total_rows = pf.metadata.num_rows

        batches = pf.iter_batches(batch_size=max_rows)
        first_batch = next(batches, None)
        rows: list[list[Any]] = []
        if first_batch:
            pydict = first_batch.to_pydict()
            for i in range(min(max_rows, len(first_batch))):
                row = []
                for col in columns:
                    val = pydict[col][i]
                    if val is None or isinstance(val, (int, float, str, bool)):
                        row.append(val)
                    else:
                        row.append(str(val))
                rows.append(row)

        return {
            "filename": filename,
            "format": "parquet",
            "columns": columns,
            "rows": rows,
            "total_rows": total_rows,
        }
    else:
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

