"""Exit 127 when a required executable is not on PATH.

PowerShell raises CommandNotFoundException for a missing command and can still
leave the process exit code at 0, which is how a missing ``docker`` binary was
reported as a successful build. Call this before shelling out.
"""

from __future__ import annotations

import shutil
import sys


def main(argv: list[str] | None = None) -> int:
    names = list(sys.argv[1:] if argv is None else argv)
    if not names:
        print("usage: require_command.py <name> [<name> ...]", file=sys.stderr)
        return 2
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        print("missing command: " + ", ".join(missing), file=sys.stderr)
        return 127
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
