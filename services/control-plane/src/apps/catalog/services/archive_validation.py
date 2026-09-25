import tarfile
import zipfile
from pathlib import PurePosixPath

from rest_framework.exceptions import ValidationError

DEFAULT_MAX_FILES = 1000
DEFAULT_MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024  # 1 GB


def validate_tar_archive(
    file_or_path,
    max_files=DEFAULT_MAX_FILES,
    max_uncompressed_bytes=DEFAULT_MAX_UNCOMPRESSED_BYTES,
):
    """Inspect a .tar.gz archive stream or path for path traversal, symlinks, and zip-bombs."""
    open_kwargs = {"name": file_or_path} if isinstance(file_or_path, str) else {"fileobj": file_or_path}
    try:
        with tarfile.open(**open_kwargs, mode="r:*") as archive:
            file_count = 0
            total_bytes = 0
            for member in archive.getmembers():
                file_count += 1
                if file_count > max_files:
                    raise ValidationError(
                        {"file": f"Archive exceeds maximum allowed file count ({max_files})."}
                    )

                # Check path traversal
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts:
                    raise ValidationError(
                        {"file": f"Archive contains an unsafe path: {member.name}"}
                    )

                # Check links
                if member.islnk() or member.issym():
                    raise ValidationError(
                        {"file": f"Archive contains symbolic or hard links, which are not allowed: {member.name}"}
                    )

                total_bytes += member.size
                if total_bytes > max_uncompressed_bytes:
                    raise ValidationError(
                        {"file": f"Archive uncompressed size exceeds maximum allowed limit ({max_uncompressed_bytes} bytes)."}
                    )

            return file_count, total_bytes
    except tarfile.TarError as exc:
        raise ValidationError({"file": f"Invalid tar archive: {str(exc)}"}) from exc


def validate_zip_archive(
    file_or_path,
    max_files=DEFAULT_MAX_FILES,
    max_uncompressed_bytes=DEFAULT_MAX_UNCOMPRESSED_BYTES,
):
    """Inspect a .zip archive stream or path for path traversal, symlinks, and zip-bombs."""
    try:
        with zipfile.ZipFile(file_or_path, mode="r") as archive:
            file_count = 0
            total_bytes = 0
            for member in archive.infolist():
                file_count += 1
                if file_count > max_files:
                    raise ValidationError(
                        {"file": f"Archive exceeds maximum allowed file count ({max_files})."}
                    )

                # Check path traversal
                path = PurePosixPath(member.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise ValidationError(
                        {"file": f"Archive contains an unsafe path: {member.filename}"}
                    )

                # Check symlink (Unix attribute 0o120000)
                is_symlink = (member.external_attr >> 16) & 0o120000 == 0o120000
                if is_symlink:
                    raise ValidationError(
                        {"file": f"Archive contains symbolic links, which are not allowed: {member.filename}"}
                    )

                total_bytes += member.file_size
                if total_bytes > max_uncompressed_bytes:
                    raise ValidationError(
                        {"file": f"Archive uncompressed size exceeds maximum allowed limit ({max_uncompressed_bytes} bytes)."}
                    )

            return file_count, total_bytes
    except zipfile.BadZipFile as exc:
        raise ValidationError({"file": f"Invalid zip archive: {str(exc)}"}) from exc
