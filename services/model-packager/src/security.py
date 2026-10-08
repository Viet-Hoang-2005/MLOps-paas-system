"""Security scanning utilities for model packages and artifacts.

Provides static inspection to protect model packaging environments against:
- ZipSlip / TarSlip path traversals and dangerous symlinks
- Decompression bombs (Zip bombs)
- Unauthorized executable / script binaries
- Arbitrary code execution via malicious pickle instructions (RCE)
- Untrusted dependency specifications
"""

import io
import os
import pickletools
import re
import tarfile
import zipfile
from pathlib import Path

# Modules that must never be referenced by deserialized ML model pickles
DANGEROUS_MODULES = frozenset(
    {
        "os",
        "posix",
        "nt",
        "subprocess",
        "sys",
        "shutil",
        "socket",
        "pty",
        "ctypes",
        "urllib",
        "requests",
        "http",
        "webbrowser",
        "commands",
        "platform",
        "importlib",
        "multiprocessing",
        "concurrent",
        "asyncio",
        "threading",
        "pickle",
        "_pickle",
    }
)

# Built-in functions that allow code execution or filesystem access
DANGEROUS_BUILTINS = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "open",
        "__import__",
        "getattr",
        "setattr",
        "delattr",
        "breakpoint",
        "input",
        "exit",
        "quit",
        "globals",
        "locals",
        "system",
    }
)

# File extensions prohibited in model artifacts
DANGEROUS_FILE_EXTENSIONS = frozenset(
    {
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".sh",
        ".bat",
        ".cmd",
        ".ps1",
        ".vbs",
        ".elf",
        ".app",
        ".msi",
        ".jar",
        ".com",
        ".hta",
        ".scr",
        ".pif",
        ".cpl",
    }
)

# Standard package naming pattern according to PEP 508
SAFE_REQUIREMENT_LINE_REGEX = re.compile(
    r"^[a-zA-Z0-9_\-\.]+(\[[a-zA-Z0-9_\-\.,\s]+\])?(\s*([~=><!^]{1,2}\s*[a-zA-Z0-9_\-\.\*]+(\s*,\s*[~=><!^]{1,2}\s*[a-zA-Z0-9_\-\.\*]+)*))?$"
)


class PackageSecurityError(ValueError):
    """Raised when an uploaded package violates security policies."""

    pass


SecurityError = PackageSecurityError


def validate_safe_requirements(requirements_text: str) -> None:
    """Validate that requirements.txt does not contain URL sources or unsafe flags."""
    if not requirements_text:
        return

    for raw_line in requirements_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # Check for disallowed pip options
        lower_line = line.lower()
        disallowed_prefixes = (
            "-e",
            "--editable",
            "--extra-index-url",
            "--index-url",
            "--find-links",
            "-f",
            "--trusted-host",
            "--process-dependency-links",
        )
        for prefix in disallowed_prefixes:
            if lower_line.startswith(prefix):
                raise PackageSecurityError(
                    f"Disallowed pip option in requirements: '{line}'"
                )

        # Check for remote URL protocols or local paths
        disallowed_schemes = (
            "git+",
            "http://",
            "https://",
            "ftp://",
            "svn://",
            "hg://",
            "file://",
        )
        if any(scheme in lower_line for scheme in disallowed_schemes):
            raise PackageSecurityError(
                f"URL and VCS dependencies are not allowed in requirements: '{line}'"
            )

        # Check for path traversal or local file references
        if line.startswith((".", "/", "\\")) or ".." in line:
            raise PackageSecurityError(
                f"Local path references are not allowed in requirements: '{line}'"
            )

        # Check for command injection shell characters
        if any(char in line for char in (";", "&", "|", "`", "$")):
            raise PackageSecurityError(
                f"Invalid characters detected in requirement: '{line}'"
            )

        # Check against standard package specification pattern
        # Strip comments at end of line if present
        clean_spec = line.split("#", 1)[0].strip()
        if not SAFE_REQUIREMENT_LINE_REGEX.match(clean_spec):
            raise PackageSecurityError(
                f"Suspicious requirement specification: '{line}'"
            )


def scan_pickle_data(data: bytes, source_name: str = "pickle") -> None:
    """Scan raw pickle bytes for malicious opcodes without executing unpickle."""
    stack: list[str] = []
    memo: dict[int, str] = {}
    try:
        for op, arg, _ in pickletools.genops(data):
            if op.name in ("SHORT_BINUNICODE", "BINUNICODE", "UNICODE", "STRING"):
                stack.append(str(arg))
            elif op.name == "MEMOIZE":
                if stack:
                    memo[len(memo)] = stack[-1]
            elif op.name in ("PUT", "BINPUT", "LONG_BINPUT"):
                if stack and arg is not None:
                    try:
                        memo[int(arg)] = stack[-1]
                    except (ValueError, TypeError):
                        pass
            elif op.name in ("GET", "BINGET", "LONG_BINGET"):
                if arg is not None:
                    try:
                        idx = int(arg)
                        if idx in memo:
                            stack.append(memo[idx])
                    except (ValueError, TypeError):
                        pass
            elif op.name == "STACK_GLOBAL":
                if len(stack) >= 2:
                    name = stack.pop()
                    module = stack.pop()
                    _check_global_symbol(module, name, source_name)
            elif op.name == "GLOBAL":
                parts = str(arg).split(" ", 1)
                module = parts[0]
                name = parts[1] if len(parts) > 1 else ""
                _check_global_symbol(module, name, source_name)
    except PackageSecurityError:
        raise
    except Exception:
        # Non-pickle byte sequence or mock artifact. If any dangerous opcodes were present,
        # _check_global_symbol would have already raised PackageSecurityError.
        pass


def _check_global_symbol(module: str, name: str, source_name: str) -> None:
    """Verify resolved global symbol against dangerous lists."""
    module_parts = module.split(".")
    root_module = module_parts[0].lower()

    if root_module in DANGEROUS_MODULES:
        raise PackageSecurityError(
            f"Dangerous pickle opcode detected in {source_name}: reference to disallowed module '{module}' (symbol: '{name}')"
        )

    if root_module in ("builtins", "__builtin__") and name in DANGEROUS_BUILTINS:
        raise PackageSecurityError(
            f"Dangerous pickle opcode detected in {source_name}: reference to disallowed builtin '{module}.{name}'"
        )


def validate_pickle_file(file_path: Path) -> None:
    """Scan a pickle or PyTorch model file for malicious instructions."""
    if not file_path.is_file():
        return

    data = file_path.read_bytes()
    # Check if this is a PyTorch ZIP container
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
                for member in archive.infolist():
                    if member.filename.endswith((".pkl", ".pickle")):
                        member_bytes = archive.read(member.filename)
                        scan_pickle_data(
                            member_bytes, f"{file_path.name}:{member.filename}"
                        )
            return
        except PackageSecurityError:
            raise
        except Exception:
            # Fall back to raw scanning if zip parsing fails
            pass

    scan_pickle_data(data, file_path.name)


def validate_archive_structure(
    archive_path: Path,
    max_files: int = 5000,
    max_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024,
) -> None:
    """Validate archive structure against ZipSlip, symlinks, and decompression bombs."""
    if not archive_path.is_file():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, "r") as archive:
            members = archive.infolist()
            if len(members) > max_files:
                raise PackageSecurityError(
                    f"Archive exceeds maximum file count limit ({len(members)} > {max_files})"
                )

            total_size = sum(m.file_size for m in members)
            if total_size > max_uncompressed_bytes:
                raise PackageSecurityError(
                    f"Archive uncompressed size exceeds limit ({total_size} > {max_uncompressed_bytes} bytes)"
                )

            for member in members:
                # Disallow symbolic links (UNIX mode 0o120000)
                is_symlink = (member.external_attr >> 16) & 0o170000 == 0o120000
                if is_symlink:
                    raise PackageSecurityError(
                        f"Archive contains unsupported symbolic link: {member.filename}"
                    )

                # Check path traversal
                filename = member.filename
                if (
                    filename.startswith(("/", "\\"))
                    or ":/" in filename
                    or ":\\" in filename
                    or ".." in Path(filename).parts
                ):
                    raise PackageSecurityError(
                        f"Archive contains unsafe path traversal: {member.filename}"
                    )

                # Check compression ratio for zip bomb defense
                if member.compress_size > 0:
                    ratio = member.file_size / member.compress_size
                    if ratio > 100 and member.file_size > 10 * 1024 * 1024:
                        raise PackageSecurityError(
                            f"Potential compression bomb detected in {member.filename} (ratio: {ratio:.1f}x)"
                        )

    elif tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, "r:*") as archive:
            members = archive.getmembers()
            if len(members) > max_files:
                raise PackageSecurityError(
                    f"Archive exceeds maximum file count limit ({len(members)} > {max_files})"
                )

            total_size = sum(m.size for m in members)
            if total_size > max_uncompressed_bytes:
                raise PackageSecurityError(
                    f"Archive uncompressed size exceeds limit ({total_size} > {max_uncompressed_bytes} bytes)"
                )

            for member in members:
                if member.islnk() or member.issym():
                    raise PackageSecurityError(
                        f"Archive contains unsupported link: {member.name}"
                    )
                name = member.name
                if (
                    name.startswith(("/", "\\"))
                    or ":/" in name
                    or ":\\" in name
                    or ".." in Path(name).parts
                ):
                    raise PackageSecurityError(
                        f"Archive contains unsafe path traversal: {member.name}"
                    )


def validate_no_dangerous_binaries(directory: Path) -> None:
    """Scan directory recursively to ensure no executable binaries or scripts exist."""
    if not directory.exists():
        return

    for item in directory.rglob("*"):
        if item.is_file():
            if item.suffix.lower() in DANGEROUS_FILE_EXTENSIONS:
                raise PackageSecurityError(
                    f"Prohibited executable or script binary detected: {item.name}"
                )


def validate_model_package_security(
    archive_or_file_path: Path,
    extract_dir: Path | None = None,
    requirements_text: str | None = None,
) -> None:
    """Comprehensive security check on uploaded model archive or directory."""
    if archive_or_file_path.is_file():
        if zipfile.is_zipfile(archive_or_file_path):
            validate_archive_structure(archive_or_file_path)
            with zipfile.ZipFile(archive_or_file_path, "r") as archive:
                for member in archive.infolist():
                    name = member.filename
                    suffix = Path(name).suffix.lower()
                    if suffix in DANGEROUS_FILE_EXTENSIONS:
                        raise PackageSecurityError(
                            f"Prohibited executable or script detected in archive: {name}"
                        )
                    if suffix in (".pkl", ".pickle", ".joblib"):
                        data = archive.read(name)
                        scan_pickle_data(data, f"{archive_or_file_path.name}:{name}")
                    if Path(name).name == "requirements.txt":
                        try:
                            req_content = archive.read(name).decode("utf-8")
                            validate_safe_requirements(req_content)
                        except UnicodeDecodeError:
                            pass
        elif tarfile.is_tarfile(archive_or_file_path):
            validate_archive_structure(archive_or_file_path)
            with tarfile.open(archive_or_file_path, "r:*") as archive:
                for member in archive.getmembers():
                    name = member.name
                    suffix = Path(name).suffix.lower()
                    if suffix in DANGEROUS_FILE_EXTENSIONS:
                        raise PackageSecurityError(
                            f"Prohibited executable or script detected in archive: {name}"
                        )
                    if suffix in (".pkl", ".pickle", ".joblib") and member.isreg():
                        extracted = archive.extractfile(member)
                        if extracted:
                            scan_pickle_data(
                                extracted.read(),
                                f"{archive_or_file_path.name}:{name}",
                            )
                    if Path(name).name == "requirements.txt" and member.isreg():
                        extracted = archive.extractfile(member)
                        if extracted:
                            try:
                                req_content = extracted.read().decode("utf-8")
                                validate_safe_requirements(req_content)
                            except UnicodeDecodeError:
                                pass
        elif archive_or_file_path.suffix.lower() in (
            ".pkl",
            ".pickle",
            ".joblib",
            ".pt",
            ".pth",
        ):
            validate_pickle_file(archive_or_file_path)

    if extract_dir and extract_dir.exists():
        validate_no_dangerous_binaries(extract_dir)

    if requirements_text:
        validate_safe_requirements(requirements_text)
