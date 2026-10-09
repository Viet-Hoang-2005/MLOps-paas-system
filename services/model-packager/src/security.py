"""Security scanning utilities for model packages and artifacts.

Provides static inspection to protect model packaging environments against:
- ZipSlip / TarSlip path traversals and dangerous symlinks
- Decompression bombs (Zip bombs)
- Unauthorized executable / script binaries
- Arbitrary code execution via malicious pickle instructions (RCE)
- Untrusted dependency specifications
"""

import _compat_pickle
import io
import pickle
import pickletools
import re
import tarfile
import zipfile
from pathlib import Path

# Pickle allowlist. A model pickle may only reference the globals below; every
# other global (os, subprocess, runpy, builtins.eval, ...) is rejected, so new
# dangerous modules never need to be listed by hand.
_CLASS_NAME = re.compile(r"^_?[A-Z][A-Za-z0-9]*$")
_PLAIN_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Module trees where any CapWords class may be referenced (no functions, no
# imported modules, no dotted attribute paths).
ALLOWED_CLASS_MODULES = (
    "sklearn.base", "sklearn.calibration", "sklearn.cluster", "sklearn.compose",
    "sklearn.covariance", "sklearn.cross_decomposition", "sklearn.decomposition",
    "sklearn.discriminant_analysis", "sklearn.dummy", "sklearn.ensemble",
    "sklearn.feature_extraction", "sklearn.feature_selection", "sklearn.gaussian_process",
    "sklearn.impute", "sklearn.isotonic", "sklearn.kernel_approximation",
    "sklearn.kernel_ridge", "sklearn.linear_model", "sklearn.manifold", "sklearn.mixture",
    "sklearn.model_selection", "sklearn.multiclass", "sklearn.multioutput",
    "sklearn.naive_bayes", "sklearn.neighbors", "sklearn.neural_network", "sklearn.pipeline",
    "sklearn.preprocessing", "sklearn.semi_supervised", "sklearn.svm", "sklearn.tree",
    "sklearn.metrics._scorer", "sklearn.metrics._dist_metrics", "sklearn.utils._bunch", "sklearn._loss", "_loss",
    "xgboost",
    "pandas.core",
    "torch.nn",
)

_NUMPY_NAMES = frozenset(
    {
        "dtype", "ndarray", "matrix", "float16", "float32", "float64", "int8", "int16",
        "int32", "int64", "uint8", "uint16", "uint32", "uint64", "bool_", "complex64",
        "complex128", "object_", "str_",
    }
)
_NUMPY_INTERNALS = frozenset({"_reconstruct", "scalar", "_frombuffer", "_mareconstruct"})
_TORCH_DTYPES = frozenset(
    {
        "float16", "float32", "float64", "bfloat16", "int8", "int16", "int32", "int64",
        "uint8", "bool", "complex64", "complex128",
    }
)
_TORCH_STORAGES = frozenset(
    {
        "FloatStorage", "DoubleStorage", "HalfStorage", "BFloat16Storage", "LongStorage",
        "IntStorage", "ShortStorage", "CharStorage", "ByteStorage", "BoolStorage",
    }
)

_TORCH_ACTIVATIONS = frozenset(
    {
        "relu", "relu6", "gelu", "silu", "elu", "selu", "leaky_relu", "sigmoid", "tanh",
        "softmax", "log_softmax", "softplus", "hardtanh", "mish",
    }
)

# Exact (module -> symbols) pairs for helpers and containers that carry no code.
ALLOWED_GLOBALS: dict[str, frozenset[str]] = {
    "builtins": frozenset(
        {
            "set", "frozenset", "list", "dict", "tuple", "int", "float", "complex", "str",
            "bytes", "bytearray", "bool", "slice", "range", "object",
        }
    ),
    "collections": frozenset({"OrderedDict", "defaultdict", "deque", "Counter"}),
    "copyreg": frozenset({"_reconstructor", "__newobj__"}),
    "_codecs": frozenset({"encode"}),
    "datetime": frozenset({"datetime", "date", "time", "timedelta", "timezone"}),
    "decimal": frozenset({"Decimal"}),
    "fractions": frozenset({"Fraction"}),
    "joblib.numpy_pickle": frozenset({"NumpyArrayWrapper", "NDArrayWrapper"}),
    "joblib.numpy_pickle_compat": frozenset({"NDArrayWrapper", "ZNDArrayWrapper"}),
    "numpy": _NUMPY_NAMES,
    "numpy.core.multiarray": _NUMPY_INTERNALS,
    "numpy._core.multiarray": _NUMPY_INTERNALS,
    "numpy.core.numeric": _NUMPY_INTERNALS,
    "numpy._core.numeric": _NUMPY_INTERNALS,
    "numpy.ma.core": frozenset({"_mareconstruct", "MaskedArray"}),
    "numpy.random._pickle": frozenset(
        {"__randomstate_ctor", "__bit_generator_ctor", "__generator_ctor"}
    ),
    "numpy.random.mtrand": frozenset({"RandomState"}),
    "numpy.random._mt19937": frozenset({"MT19937"}),
    "numpy.random._pcg64": frozenset({"PCG64", "PCG64DXSM"}),
    "pandas._libs.internals": frozenset({"_unpickle_block"}),
    "pandas.core.indexes.base": frozenset({"_new_Index"}),
    "scipy.sparse._csr": frozenset({"csr_matrix", "csr_array"}),
    "scipy.sparse._csc": frozenset({"csc_matrix", "csc_array"}),
    "scipy.sparse._coo": frozenset({"coo_matrix", "coo_array"}),
    "scipy.sparse.csr": frozenset({"csr_matrix"}),
    "scipy.sparse.csc": frozenset({"csc_matrix"}),
    "torch": frozenset({"Size", "device", "Tensor"} | _TORCH_DTYPES | _TORCH_STORAGES),
    "torch._tensor": frozenset({"Tensor", "_rebuild_from_type_v2"}),
    "torch._utils": frozenset(
        {"_rebuild_tensor", "_rebuild_tensor_v2", "_rebuild_parameter", "_rebuild_parameter_with_state"}
    ),
    "torch.storage": frozenset({"TypedStorage", "UntypedStorage"}),
    "torch.nn.functional": _TORCH_ACTIVATIONS,
    # Cython helpers that rebuild KD/ball trees and distance metrics, and plain selectors.
    "sklearn.neighbors._kd_tree": frozenset({"newObj"}),
    "sklearn.neighbors._ball_tree": frozenset({"newObj"}),
    "sklearn.metrics._dist_metrics": frozenset({"newObj"}),
    "sklearn.compose._column_transformer": frozenset({"make_column_selector"}),
    "sklearn.feature_selection._univariate_selection": frozenset(
        {"f_classif", "f_regression", "chi2", "f_oneway"}
    ),
    "sklearn.feature_selection._mutual_info": frozenset({"mutual_info_classif", "mutual_info_regression"}),
}

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


_STRING_OPS = frozenset(
    {"STRING", "BINSTRING", "SHORT_BINSTRING", "UNICODE", "BINUNICODE", "SHORT_BINUNICODE", "BINUNICODE8"}
)
_JOBLIB_ARRAY_MODULES = frozenset({"joblib.numpy_pickle", "joblib.numpy_pickle_compat"})
_COMPRESSION_MAGIC = (b"\x78", b"\x1f\x8b", b"BZh", b"\xfd7zXZ", b"\x5d\x00", b"\x04\x22\x4d\x18")
_UNKNOWN = object()
_MARK = object()


# Only these are really resolved while verifying a joblib stream (joblib needs
# real numpy arrays); every other allowlisted class is replaced by _InertClass.
_REAL_MODULE_ROOTS = frozenset(
    {"numpy", "joblib", "builtins", "collections", "copyreg", "_codecs", "datetime", "decimal", "fractions"}
)


class _InertClass:
    def __new__(cls, *args, **kwargs):
        return object.__new__(cls)

    def __init__(self, *args, **kwargs):
        pass

    def __setstate__(self, state):
        pass

    # Placeholders for dict/list/set subclasses (e.g. sklearn Bunch) must accept
    # the items the pickle fills in.
    def __setitem__(self, key, value):
        pass

    def append(self, value):
        pass

    def extend(self, values):
        pass

    def update(self, *args, **kwargs):
        pass

    def add(self, value):
        pass


class _MalformedPickle(Exception):
    pass


def _in_module_tree(module: str, root: str) -> bool:
    return module == root or module.startswith(root + ".")


def is_allowed_global(module: str, name: str) -> bool:
    """Return True when a pickle may reference ``module.name``."""
    if not _PLAIN_NAME.match(module.replace(".", "_")) or not _PLAIN_NAME.match(name):
        return False
    if name in ALLOWED_GLOBALS.get(module, ()):
        return True
    if _CLASS_NAME.match(name) and any(_in_module_tree(module, root) for root in ALLOWED_CLASS_MODULES):
        return True
    return module.startswith("numpy.dtypes") and name.endswith("DType") and _CLASS_NAME.match(name) is not None


def _normalize_global(module: str, name: str) -> tuple[str, str]:
    """Apply the Python 2 name mapping the unpickler uses for protocol < 3 pickles."""
    if (module, name) in _compat_pickle.NAME_MAPPING:
        return _compat_pickle.NAME_MAPPING[(module, name)]
    return _compat_pickle.IMPORT_MAPPING.get(module, module), name


def _check_global_symbol(module: str, name: str, source_name: str) -> None:
    """Reject any global that is not on the allowlist."""
    module, name = _normalize_global(module, name)
    if is_allowed_global(module, name):
        return
    known = module in ALLOWED_GLOBALS or any(_in_module_tree(module, root) for root in ALLOWED_CLASS_MODULES)
    if module in ("builtins", "__builtin__"):
        kind = "builtin"
        target = f"{module}.{name}"
    elif known:
        kind = "symbol"
        target = f"{module}.{name}"
    else:
        kind = "module"
        target = f"{module}' (symbol: '{name}"
    raise PackageSecurityError(
        f"Dangerous pickle opcode detected in {source_name}: reference to disallowed {kind} '{target}'"
    )


def _split_global(arg) -> tuple[str, str]:
    parts = str(arg).split(" ", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def _walk_pickle(data: bytes, source_name: str, single_pickle: bool = False) -> bool:
    """Check every global with a simulated stack. Returns True if joblib arrays were met.

    Joblib writes raw array bytes inside the stream, so the walk stops there and
    the stream is verified by a restricted joblib unpickler instead.
    """
    stack: list = []
    marks: list[int] = []
    memo: dict[int, object] = {}
    try:
        for op, arg, pos in pickletools.genops(data):
            name = op.name
            if name in _STRING_OPS:
                stack.append(arg if isinstance(arg, str) else _UNKNOWN)
                continue
            if name == "MARK":
                marks.append(len(stack))
                stack.append(_MARK)
                continue
            if name in ("GLOBAL", "INST"):
                module, symbol = _split_global(arg)
                _check_global_symbol(module, symbol, source_name)
                if module in _JOBLIB_ARRAY_MODULES:
                    return True
            elif name == "STACK_GLOBAL":
                if len(stack) < 2 or not all(isinstance(item, str) for item in stack[-2:]):
                    raise PackageSecurityError(
                        f"Dangerous pickle opcode detected in {source_name}: non-literal global reference"
                    )
                module, symbol = stack[-2], stack[-1]
                _check_global_symbol(module, symbol, source_name)
                if module in _JOBLIB_ARRAY_MODULES:
                    return True
            elif name in ("EXT1", "EXT2", "EXT4"):
                raise PackageSecurityError(
                    f"Dangerous pickle opcode detected in {source_name}: extension registry references are not allowed"
                )
            elif name in ("GET", "BINGET", "LONG_BINGET"):
                stack.append(memo.get(int(arg), _UNKNOWN))
                continue
            elif name == "DUP":
                stack.append(stack[-1])
                continue
            elif name == "MEMOIZE":
                memo[len(memo)] = stack[-1]
                continue
            elif name in ("PUT", "BINPUT", "LONG_BINPUT"):
                memo[int(arg)] = stack[-1]
                continue
            elif name == "STOP":
                if single_pickle and pos + 1 < len(data):
                    # torch.load keeps reading pickles after the first STOP (legacy format),
                    # so anything after it would run without having been scanned.
                    raise PackageSecurityError(
                        f"Unsupported multi-pickle file {source_name}: re-save it with the default torch.save"
                    )
                return False

            before = op.stack_before
            if pickletools.markobject in before:
                if not marks:
                    raise _MalformedPickle
                del stack[marks.pop():]
                below = before.index(pickletools.markobject)
                if below:
                    del stack[-below:]
            elif before:
                del stack[-len(before):]
            stack.extend(_UNKNOWN for _ in op.stack_after)
    except PackageSecurityError:
        raise
    except Exception as exc:
        raise _MalformedPickle from exc
    return False


def _restricted_find_class(base_find_class, module: str, name: str, source_name: str):
    _check_global_symbol(module, name, source_name)
    if _normalize_global(module, name)[0].split(".")[0] in _REAL_MODULE_ROOTS:
        return base_find_class(module, name)
    # Third-party classes are never imported or run, only walked past.
    return _InertClass


class _RestrictedPickleModule:
    """Stand-in for ``pickle`` inside joblib: object arrays embed a nested pickle that
    joblib reads with ``pickle.load``, which must obey the same allowlist."""

    def __init__(self, source_name: str):
        self._source_name = source_name

    def __getattr__(self, name):
        return getattr(pickle, name)

    def load(self, file, **_kwargs):
        source_name = self._source_name

        class Restricted(pickle.Unpickler):
            def find_class(self, module, name):
                return _restricted_find_class(super().find_class, module, name, source_name)

        return Restricted(file).load()


def _verify_joblib_stream(data: bytes, source_name: str) -> None:
    """Load a joblib stream with an allowlist-only unpickler (arrays are read, code is not run)."""
    try:
        from joblib import numpy_pickle
    except ImportError as exc:
        raise PackageSecurityError(f"Cannot verify joblib artifact {source_name}: joblib is unavailable") from exc

    class RestrictedUnpickler(numpy_pickle.NumpyUnpickler):
        def find_class(self, module, name):
            return _restricted_find_class(super().find_class, module, name, source_name)

    original_pickle = numpy_pickle.pickle
    numpy_pickle.pickle = _RestrictedPickleModule(source_name)
    try:
        with numpy_pickle._read_fileobject(io.BytesIO(data), source_name, None) as handle:
            RestrictedUnpickler(source_name, handle, mmap_mode=None).load()
    except PackageSecurityError:
        raise
    except Exception as exc:
        raise PackageSecurityError(f"Cannot verify joblib artifact {source_name}: {type(exc).__name__}") from exc
    finally:
        numpy_pickle.pickle = original_pickle


def scan_pickle_data(data: bytes, source_name: str = "pickle", single_pickle: bool = False) -> None:
    """Check a pickle against the global allowlist without running its code.

    Anything that cannot be parsed is rejected rather than assumed to be safe.
    """
    try:
        if _walk_pickle(data, source_name, single_pickle):
            _verify_joblib_stream(data, source_name)
    except _MalformedPickle:
        if data.startswith(_COMPRESSION_MAGIC):
            _verify_joblib_stream(data, source_name)
            return
        raise PackageSecurityError(f"Could not verify pickle structure of {source_name}") from None


# Serialized model suffixes that are loaded through pickle (PyTorch .pt/.pth
# checkpoints are pickles, usually inside a zip container).
PICKLE_MODEL_SUFFIXES = (".pkl", ".pickle", ".joblib", ".pt", ".pth")


def scan_model_bytes(data: bytes, label: str, single_pickle: bool = False) -> None:
    """Scan raw pickle or PyTorch container bytes for malicious instructions."""
    # Check if this is a PyTorch ZIP container
    if data.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
                for member in archive.infolist():
                    if member.filename.endswith((".pkl", ".pickle")):
                        member_bytes = archive.read(member.filename)
                        scan_pickle_data(member_bytes, f"{label}:{member.filename}")
            return
        except PackageSecurityError:
            raise
        except Exception:
            # Fall back to raw scanning if zip parsing fails
            pass

    scan_pickle_data(data, label, single_pickle)


def validate_pickle_file(file_path: Path) -> None:
    """Scan a pickle or PyTorch model file for malicious instructions."""
    if not file_path.is_file():
        return
    scan_model_bytes(file_path.read_bytes(), file_path.name, _is_torch_suffix(file_path.name))


def _is_torch_suffix(name: str) -> bool:
    return Path(name).suffix.lower() in (".pt", ".pth")


# Members of these kinds are not pickles; everything else is sniffed, so renaming
# model.pkl to weights.dat does not skip the scan.
SAFE_MEMBER_SUFFIXES = frozenset(
    {
        ".json", ".yaml", ".yml", ".txt", ".md", ".csv", ".npy", ".npz", ".safetensors", ".onnx",
        ".pb", ".pbtxt", ".h5", ".keras", ".xgb", ".ubj", ".index", ".lock", ".cfg", ".ini",
        ".toml", ".tflite", ".proto",
    }
)
MAX_SNIFFED_MEMBER_BYTES = 256 * 1024 * 1024
ALLOWED_MLFLOW_LOADERS = frozenset(
    {"mlflow.sklearn", "mlflow.xgboost", "mlflow.pytorch", "mlflow.tensorflow", "mlflow.keras"}
)


def _looks_like_pickle(data: bytes) -> bool:
    if len(data) > 1 and data[0] == 0x80 and 2 <= data[1] <= 5:
        return True
    try:
        return any(op.name == "STOP" for op, _arg, _pos in pickletools.genops(data))
    except Exception:
        return False


def _scan_archive_member(name: str, size: int, read_bytes, label: str) -> None:
    """Scan one archive member as a pickle if it is one, whatever its file name says."""
    suffix = Path(name).suffix.lower()
    if suffix in PICKLE_MODEL_SUFFIXES:
        scan_model_bytes(read_bytes(), label, _is_torch_suffix(name))
        return
    if suffix in SAFE_MEMBER_SUFFIXES or suffix.startswith(".data-"):
        return
    if size > MAX_SNIFFED_MEMBER_BYTES:
        raise PackageSecurityError(f"Cannot verify large file with unknown type in archive: {name}")
    data = read_bytes()
    if _looks_like_pickle(data):
        scan_model_bytes(data, label)


def _validate_mlmodel(text: str, label: str) -> None:
    """MLflow imports `loader_module` and adds `code/` to sys.path when loading a model."""
    try:
        import yaml

        config = yaml.safe_load(text)
    except Exception as exc:
        raise PackageSecurityError(f"Cannot verify MLmodel file {label}") from exc
    if not isinstance(config, dict):
        raise PackageSecurityError(f"Cannot verify MLmodel file {label}")
    pyfunc = (config.get("flavors") or {}).get("python_function") or {}
    loader = pyfunc.get("loader_module")
    if loader is not None and loader not in ALLOWED_MLFLOW_LOADERS:
        raise PackageSecurityError(f"MLmodel in {label} uses a disallowed loader_module: {loader}")
    if pyfunc.get("code"):
        raise PackageSecurityError(f"MLmodel in {label} bundles custom code, which is not allowed")


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
                    if not member.is_dir():
                        _scan_archive_member(
                            name,
                            member.file_size,
                            lambda n=name: archive.read(n),
                            f"{archive_or_file_path.name}:{name}",
                        )
                    if Path(name).name == "MLmodel":
                        _validate_mlmodel(
                            archive.read(name).decode("utf-8", "replace"),
                            f"{archive_or_file_path.name}:{name}",
                        )
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
                    if member.isreg():
                        extracted = archive.extractfile(member)
                        if extracted:
                            _scan_archive_member(
                                name, member.size, extracted.read, f"{archive_or_file_path.name}:{name}"
                            )
                        if Path(name).name == "MLmodel":
                            mlmodel = archive.extractfile(member)
                            if mlmodel:
                                _validate_mlmodel(
                                    mlmodel.read().decode("utf-8", "replace"),
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
        elif archive_or_file_path.suffix.lower() in PICKLE_MODEL_SUFFIXES:
            validate_pickle_file(archive_or_file_path)

    if extract_dir and extract_dir.exists():
        validate_no_dangerous_binaries(extract_dir)

    if requirements_text:
        validate_safe_requirements(requirements_text)
