"""A missing executable must be a failed process, not a swallowed error."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "require_command.py"
PS1 = Path(__file__).resolve().parents[1] / "scripts" / "require-command.ps1"
MISSING = "no-such-command-lexproof"


def test_python_require_command_exits_127_when_missing():
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), MISSING],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 127
    assert MISSING in completed.stderr


def test_python_require_command_accepts_python():
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "python"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0


def test_powershell_require_command_exits_127_when_missing():
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(PS1),
            MISSING,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 127
    assert MISSING in completed.stderr
