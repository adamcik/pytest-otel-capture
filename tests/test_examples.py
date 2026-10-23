import re
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("document", ["README.md", "docs/behavioral-tests.md"])
def test_documented_python_examples_run(document: str, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / document).read_text()
    blocks = re.findall(r"^```python\n(.*?)^```", text, re.MULTILINE | re.DOTALL)
    assert blocks, "document has no executable Python examples"
    example = tmp_path / "test_documented_example.py"
    example.write_text(
        "\n\n".join(blocks) + "\n\ndef test_example_completed():\n    pass\n"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(example)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
