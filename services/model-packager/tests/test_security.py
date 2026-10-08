import io
import os
import pickle
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
from src import io as packager_io
from src.security import (
    PackageSecurityError,
    scan_pickle_data,
    validate_archive_structure,
    validate_model_package_security,
    validate_no_dangerous_binaries,
    validate_pickle_file,
    validate_safe_requirements,
)


def test_validate_safe_requirements_valid():
    valid_text = """
    # Standard requirements
    numpy==1.26.0
    torch>=2.0.0,<=2.3.0
    scikit-learn~=1.3.0
    xgboost
    pandas[performance]>=1.5.0
    """
    validate_safe_requirements(valid_text)


def test_validate_safe_requirements_rejects_disallowed_flags():
    with pytest.raises(PackageSecurityError, match="Disallowed pip option"):
        validate_safe_requirements("-e .")

    with pytest.raises(PackageSecurityError, match="Disallowed pip option"):
        validate_safe_requirements("--extra-index-url https://evil.com/simple")

    with pytest.raises(PackageSecurityError, match="Disallowed pip option"):
        validate_safe_requirements("--trusted-host evil.com")


def test_validate_safe_requirements_rejects_urls_and_vcs():
    with pytest.raises(PackageSecurityError, match="URL and VCS dependencies"):
        validate_safe_requirements("git+https://github.com/evil/exploit.git")

    with pytest.raises(PackageSecurityError, match="URL and VCS dependencies"):
        validate_safe_requirements("https://evil.com/packages/trojan.whl")


def test_validate_safe_requirements_rejects_local_paths():
    with pytest.raises(PackageSecurityError, match="Local path references"):
        validate_safe_requirements("../secret_pkg")

    with pytest.raises(PackageSecurityError, match="Local path references"):
        validate_safe_requirements("./local_pkg")


def test_validate_safe_requirements_rejects_shell_injection():
    with pytest.raises(PackageSecurityError, match="Invalid characters"):
        validate_safe_requirements("numpy; cat /etc/passwd")

    with pytest.raises(PackageSecurityError, match="Invalid characters"):
        validate_safe_requirements("scikit-learn & echo pwned")

    with pytest.raises(PackageSecurityError, match="Invalid characters"):
        validate_safe_requirements("torch | evil")


def test_scan_pickle_data_safe():
    safe_data = pickle.dumps({"weights": [1.0, 2.0, 3.0], "label": "benign"})
    scan_pickle_data(safe_data, "safe.pkl")


def test_scan_pickle_data_rejects_os_system():
    class Exploit:
        def __reduce__(self):
            return (os.system, ("echo pwned",))

    bad_data = pickle.dumps(Exploit())
    with pytest.raises(PackageSecurityError, match="disallowed module"):
        scan_pickle_data(bad_data, "exploit.pkl")


def test_scan_pickle_data_rejects_subprocess():
    import subprocess

    class ExploitSubprocess:
        def __reduce__(self):
            return (subprocess.Popen, (["id"],))

    bad_data = pickle.dumps(ExploitSubprocess())
    with pytest.raises(PackageSecurityError, match="disallowed module"):
        scan_pickle_data(bad_data, "exploit_sub.pkl")


def test_scan_pickle_data_rejects_builtins_eval():
    class ExploitEval:
        def __reduce__(self):
            return (eval, ("__import__('os').system('id')",))

    bad_data = pickle.dumps(ExploitEval())
    with pytest.raises(PackageSecurityError, match="disallowed builtin"):
        scan_pickle_data(bad_data, "exploit_eval.pkl")


def test_scan_pickle_data_rejects_socket():
    import socket

    class ExploitSocket:
        def __reduce__(self):
            return (socket.socket, ())

    bad_data = pickle.dumps(ExploitSocket())
    with pytest.raises(PackageSecurityError, match="disallowed module"):
        scan_pickle_data(bad_data, "exploit_socket.pkl")


def test_validate_archive_structure_safe(tmp_path):
    zip_path = tmp_path / "valid.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("model/weights.bin", b"123")
        z.writestr("model/config.json", b"{}")
    validate_archive_structure(zip_path)


def test_validate_archive_structure_rejects_zip_slip(tmp_path):
    bad_zip = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad_zip, "w") as z:
        z.writestr("../../../etc/passwd", b"root:x:0:0")
    with pytest.raises(PackageSecurityError, match="path traversal"):
        validate_archive_structure(bad_zip)


def test_validate_archive_structure_rejects_symlink(tmp_path):
    sym_zip = tmp_path / "symlink.zip"
    with zipfile.ZipFile(sym_zip, "w") as z:
        info = zipfile.ZipInfo("symlink_file")
        # UNIX symlink attribute
        info.external_attr = 0o120777 << 16
        z.writestr(info, "/var/run/docker.sock")
    with pytest.raises(PackageSecurityError, match="symbolic link"):
        validate_archive_structure(sym_zip)


def test_validate_archive_structure_rejects_too_many_files(tmp_path):
    crowded_zip = tmp_path / "crowded.zip"
    with zipfile.ZipFile(crowded_zip, "w") as z:
        for i in range(10):
            z.writestr(f"file_{i}.txt", b"x")
    with pytest.raises(PackageSecurityError, match="file count limit"):
        validate_archive_structure(crowded_zip, max_files=5)


def test_validate_no_dangerous_binaries(tmp_path):
    (tmp_path / "safe.json").write_text("{}")
    (tmp_path / "model.pkl").write_bytes(b"data")
    validate_no_dangerous_binaries(tmp_path)

    bad_script = tmp_path / "backdoor.sh"
    bad_script.write_text("#!/bin/bash\nrm -rf /\n")
    with pytest.raises(PackageSecurityError, match="Prohibited executable"):
        validate_no_dangerous_binaries(tmp_path)

    bad_script.unlink()
    bad_exe = tmp_path / "payload.exe"
    bad_exe.write_bytes(b"MZ\x90")
    with pytest.raises(PackageSecurityError, match="Prohibited executable"):
        validate_no_dangerous_binaries(tmp_path)


def test_validate_model_package_security_end_to_end(tmp_path):
    # 1. Safe package
    good_zip = tmp_path / "good_model.zip"
    with zipfile.ZipFile(good_zip, "w") as z:
        z.writestr("model/MLmodel", "flavor: sklearn\n")
        z.writestr("model/requirements.txt", "scikit-learn==1.3.0\n")
        z.writestr("model/model.pkl", pickle.dumps({"weights": [1, 2]}))
    validate_model_package_security(good_zip)

    # 2. Package with malicious pickle
    class Malicious:
        def __reduce__(self):
            return (os.system, ("rm -rf /",))

    bad_pickle_zip = tmp_path / "bad_pickle.zip"
    with zipfile.ZipFile(bad_pickle_zip, "w") as z:
        z.writestr("model/MLmodel", "flavor: sklearn\n")
        z.writestr("model/model.pkl", pickle.dumps(Malicious()))
    with pytest.raises(PackageSecurityError, match="disallowed module"):
        validate_model_package_security(bad_pickle_zip)

    # 3. Package with malicious binary
    bad_bin_zip = tmp_path / "bad_bin.zip"
    with zipfile.ZipFile(bad_bin_zip, "w") as z:
        z.writestr("model/script.sh", "#!/bin/sh\n")
    with pytest.raises(PackageSecurityError, match="Prohibited executable"):
        validate_model_package_security(bad_bin_zip)

    # 4. Package with malicious requirements.txt
    bad_req_zip = tmp_path / "bad_req.zip"
    with zipfile.ZipFile(bad_req_zip, "w") as z:
        z.writestr("model/requirements.txt", "git+https://github.com/evil/pkg.git\n")
    with pytest.raises(PackageSecurityError, match="URL and VCS"):
        validate_model_package_security(bad_req_zip)


def test_safe_extract_zip_rejects_symlink(tmp_path):
    sym_zip = tmp_path / "symlink_test.zip"
    with zipfile.ZipFile(sym_zip, "w") as z:
        info = zipfile.ZipInfo("symlink_to_socket")
        info.external_attr = 0o120777 << 16
        z.writestr(info, "/var/run/docker.sock")

    extract_dest = tmp_path / "out"
    with pytest.raises(ValueError, match="links"):
        packager_io.safe_extract_zip(sym_zip, extract_dest)



class _Exploit:
    def __reduce__(self):
        return (os.system, ("echo pwned",))


def _torch_container(pickle_bytes: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("archive/data.pkl", pickle_bytes)
    return buffer.getvalue()


@pytest.mark.parametrize("member_name", ["model.pt", "nested/model.pth"])
def test_validate_model_package_security_scans_pytorch_files_in_tar(tmp_path, member_name):
    archive_path = tmp_path / "training-model.tar.gz"
    payload = pickle.dumps(_Exploit())
    with tarfile.open(archive_path, "w:gz") as tar:
        info = tarfile.TarInfo(member_name)
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    with pytest.raises(PackageSecurityError, match="disallowed module"):
        validate_model_package_security(archive_path)


def test_validate_model_package_security_scans_pytorch_container_in_tar(tmp_path):
    archive_path = tmp_path / "training-model.tar.gz"
    payload = _torch_container(pickle.dumps(_Exploit()))
    with tarfile.open(archive_path, "w:gz") as tar:
        info = tarfile.TarInfo("model.pt")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    with pytest.raises(PackageSecurityError, match="disallowed module"):
        validate_model_package_security(archive_path)


def test_validate_model_package_security_scans_pytorch_files_in_zip(tmp_path):
    archive_path = tmp_path / "model.zip"
    with zipfile.ZipFile(archive_path, "w") as z:
        z.writestr("data/model.pth", pickle.dumps(_Exploit()))
    with pytest.raises(PackageSecurityError, match="disallowed module"):
        validate_model_package_security(archive_path)


def test_validate_model_package_security_accepts_benign_pytorch_files_in_tar(tmp_path):
    archive_path = tmp_path / "training-model.tar.gz"
    payload = _torch_container(pickle.dumps({"weights": [1.0, 2.0]}))
    with tarfile.open(archive_path, "w:gz") as tar:
        info = tarfile.TarInfo("model.pt")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    validate_model_package_security(archive_path)


def _unicode(value: str) -> bytes:
    return b"\x8c" + bytes([len(value)]) + value.encode()


def _stack_global_pickle(*steps: bytes) -> bytes:
    """Protocol 4 pickle that calls the resolved STACK_GLOBAL with one string argument."""
    return b"\x80\x04" + b"".join(steps) + _unicode("echo hi") + b"\x85R."


@pytest.mark.parametrize(
    "module,name",
    [("runpy", "_run_code"), ("pydoc", "pipepager"), ("code", "interact"), ("distutils.spawn", "spawn")],
)
def test_scan_pickle_data_rejects_modules_missing_from_old_denylist(module, name):
    payload = _stack_global_pickle(_unicode(module), _unicode(name), b"\x93")
    with pytest.raises(PackageSecurityError, match="disallowed module"):
        scan_pickle_data(payload, "unlisted.pkl")


def test_scan_pickle_data_rejects_symbols_outside_the_allowlist():
    with pytest.raises(PackageSecurityError, match="disallowed builtin"):
        scan_pickle_data(_stack_global_pickle(_unicode("builtins"), _unicode("getattr"), b"\x93"), "getattr.pkl")
    with pytest.raises(PackageSecurityError, match="disallowed symbol"):
        scan_pickle_data(_stack_global_pickle(_unicode("numpy"), _unicode("load"), b"\x93"), "numpy-load.pkl")
    # A dotted attribute path could walk from an allowed module to os.system.
    with pytest.raises(PackageSecurityError, match="disallowed"):
        scan_pickle_data(
            _stack_global_pickle(_unicode("sklearn.ensemble"), _unicode("os.system"), b"\x93"), "dotted.pkl"
        )
    # Functions of an allowed package are not classes.
    with pytest.raises(PackageSecurityError, match="disallowed symbol"):
        scan_pickle_data(
            _stack_global_pickle(_unicode("sklearn.ensemble"), _unicode("fetch_openml"), b"\x93"), "function.pkl"
        )


def test_scan_pickle_data_is_not_fooled_by_decoy_strings():
    # os.system is on the stack; two decoy strings are pushed and popped so a
    # naive "last two strings" scan would only ever see numpy.dtype.
    payload = _stack_global_pickle(
        _unicode("os"), _unicode("system"), _unicode("numpy"), _unicode("dtype"), b"00", b"\x93"
    )
    with pytest.raises(PackageSecurityError, match="disallowed module"):
        scan_pickle_data(payload, "decoy.pkl")


def test_scan_pickle_data_rejects_non_literal_and_extension_globals():
    with pytest.raises(PackageSecurityError, match="non-literal"):
        scan_pickle_data(b"\x80\x04N" + _unicode("dtype") + b"\x93.", "non-literal.pkl")
    with pytest.raises(PackageSecurityError, match="extension registry"):
        scan_pickle_data(b"\x80\x02\x82\x01.", "ext.pkl")


@pytest.mark.parametrize("payload", [b"not a pickle at all", b"\x80\x04\x8c\x05ab", b""])
def test_scan_pickle_data_rejects_unparseable_data(payload):
    with pytest.raises(PackageSecurityError, match="Could not verify"):
        scan_pickle_data(payload, "garbage.pkl")


_BUILD_REAL_ARTIFACTS = """
import pickle, sys
from pathlib import Path
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

out = Path(sys.argv[1])
rng = np.random.default_rng(0)
features = rng.normal(size=(60, 4))
labels = (features[:, 0] > 0).astype(int)
models = {
    "pipeline": Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression())]).fit(features, labels),
    "forest": RandomForestClassifier(n_estimators=3, random_state=0).fit(features, labels),
}
for protocol in (0, 2, 4):
    (out / f"pipeline-p{protocol}.pkl").write_bytes(pickle.dumps(models["pipeline"], protocol=protocol))
(out / "models.pkl").write_bytes(pickle.dumps(models))
joblib.dump(models, out / "models-c0.joblib", compress=0)
joblib.dump(models, out / "models-c3.joblib", compress=3)
try:
    import xgboost
    booster = xgboost.XGBClassifier(n_estimators=2).fit(features[:, :3], labels)
    (out / "xgboost.pkl").write_bytes(pickle.dumps(booster))
except ImportError:
    pass
try:
    import torch
    net = torch.nn.Sequential(torch.nn.Linear(3, 2), torch.nn.ReLU())
    torch.save(net, out / "full.pt")
    torch.save(net.state_dict(), out / "state.pth")
except ImportError:
    pass
"""


@pytest.fixture(scope="module")
def real_artifacts(tmp_path_factory):
    """Real model files, built in a clean interpreter (conftest stubs torch/xgboost)."""
    out = tmp_path_factory.mktemp("real-artifacts")
    result = subprocess.run(
        [sys.executable, "-c", _BUILD_REAL_ARTIFACTS, str(out)], capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        pytest.skip(f"could not build real artifacts: {result.stderr[-300:]}")
    return out


@pytest.mark.parametrize(
    "name",
    ["models.pkl", "pipeline-p0.pkl", "pipeline-p2.pkl", "pipeline-p4.pkl", "xgboost.pkl", "full.pt", "state.pth"],
)
def test_validate_pickle_file_accepts_real_pickled_models(real_artifacts, name):
    path = real_artifacts / name
    if not path.exists():
        pytest.skip(f"{name} unavailable in this environment")
    validate_pickle_file(path)


@pytest.mark.parametrize("name", ["models-c0.joblib", "models-c3.joblib"])
def test_validate_pickle_file_accepts_joblib_models_with_arrays(real_artifacts, name):
    validate_pickle_file(real_artifacts / name)


def test_validate_pickle_file_rejects_malicious_global_after_joblib_arrays(tmp_path):
    import joblib
    import numpy as np

    path = tmp_path / "evil.joblib"
    joblib.dump({"weights": np.arange(1000, dtype="float64"), "payload": _Exploit()}, path)
    with pytest.raises(PackageSecurityError, match="disallowed module"):
        validate_pickle_file(path)
