import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_app_code_parses_on_python_311():
    """Databricks Apps run Python 3.11: no f-string syntax that needs 3.12+."""
    files = [str(p) for p in (ROOT / "app").rglob("*.py")] + [str(p) for p in (ROOT / "src" / "analytics").glob("*.py")]
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_py311.py"), *files], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


def test_app_pins_the_databricks_sdk():
    """The Apps runtime ships an older databricks-sdk; an unpinned requirement keeps it (Genie broke on 11 Nov 2026)."""
    reqs = (Path(__file__).resolve().parent.parent / "app" / "requirements.txt").read_text().splitlines()
    sdk = [r for r in reqs if r.startswith("databricks-sdk")]
    assert sdk and "==" in sdk[0]
