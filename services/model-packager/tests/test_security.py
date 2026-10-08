import io
import os
import pickle
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

