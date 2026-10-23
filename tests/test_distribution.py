import email
import importlib.resources
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

import pytest_otel_capture as capture


def test_built_distributions_contain_metadata_types_and_license(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(tmp_path)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (wheel_path,) = tmp_path.glob("*.whl")
    (sdist_path,) = tmp_path.glob("*.tar.gz")
    license_bytes = (root / "LICENSE").read_bytes()
    with zipfile.ZipFile(wheel_path) as wheel:
        names = wheel.namelist()
        assert "pytest_otel_capture/py.typed" in names
        (metadata_path,) = (
            name for name in names if name.endswith(".dist-info/METADATA")
        )
        metadata = email.message_from_bytes(wheel.read(metadata_path))
        (license_path,) = (name for name in names if name.endswith("/licenses/LICENSE"))
        assert wheel.read(license_path) == license_bytes
        assert not any(name.endswith("entry_points.txt") for name in names)
    assert metadata["Name"] == "pytest-otel-capture"
    assert metadata["License-Expression"] == "Apache-2.0"
    assert metadata["License-File"] == "LICENSE"
    python_versions = SpecifierSet(metadata["Requires-Python"])
    assert "3.11" not in python_versions
    assert all(version in python_versions for version in ("3.12", "3.13", "3.14"))
    requirements = {
        item.name: item.specifier
        for item in map(Requirement, metadata.get_all("Requires-Dist", []))
    }
    assert set(requirements) == {"opentelemetry-api", "opentelemetry-sdk"}
    for versions in requirements.values():
        assert "1.43.0" in versions and "1.44.0" in versions
        assert "1.42.0" not in versions and "1.45.0" not in versions
    with tarfile.open(sdist_path) as sdist:
        members = {
            member.name.split("/", 1)[1]: member for member in sdist.getmembers()
        }
        assert "src/pytest_otel_capture/py.typed" in members
        license_stream = sdist.extractfile(members["LICENSE"])
        assert license_stream is not None and license_stream.read() == license_bytes
        metadata_stream = sdist.extractfile(members["PKG-INFO"])
        assert metadata_stream is not None
        source_metadata = email.message_from_bytes(metadata_stream.read())
        assert source_metadata["Version"] == metadata["Version"]
        assert source_metadata["License-Expression"] == "Apache-2.0"
    assert importlib.resources.files(capture).joinpath("py.typed").is_file()
