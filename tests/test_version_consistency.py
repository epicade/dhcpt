# Copyright (C) 2026 Emilian Schweikert
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""Validate project metadata and documentation version consistency.

Ensures that pyproject.toml, src/dhcpt/__init__.py, and man/dhcpt.1.md stay synchronized
according to Semantic Versioning (SemVer):
- Package version in pyproject.toml must match __version__ in src/dhcpt/__init__.py.
- Manpage version in man/dhcpt.1.md must not be older than pyproject.toml (fails if older).
- If manpage version is newer than pyproject.toml, a warning is emitted.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def validate_version_consistency(root_dir: Path | None = None) -> tuple[bool, str]:
    """Validate version consistency between pyproject.toml, src/dhcpt/__init__.py, and man/dhcpt.1.md.

    Args:
        root_dir: Optional repository root path. Discovered automatically if omitted.

    Returns:
        tuple[bool, str]: (is_valid, status_or_error_message).
    """
    if root_dir is None:
        candidates = [Path.cwd()]
        current_file = globals().get("__file__")
        if current_file:
            candidates.append(Path(current_file).resolve().parent.parent)
        for c in candidates:
            if (c / "pyproject.toml").is_file():
                root_dir = c
                break
        if root_dir is None:
            return False, "Could not locate repository root directory."

    pyproject_file = root_dir / "pyproject.toml"
    init_file = root_dir / "src" / "dhcpt" / "__init__.py"
    man_file = root_dir / "man" / "dhcpt.1.md"

    if not pyproject_file.is_file():
        return False, f"Missing pyproject.toml at {pyproject_file}"
    m_pkg = re.search(r'version\s*=\s*"([0-9.]+)"', pyproject_file.read_text(encoding="utf-8"))
    if not m_pkg:
        return False, "Could not extract version from pyproject.toml"
    pkg_ver = m_pkg.group(1)

    if not init_file.is_file():
        return False, f"Missing __init__.py at {init_file}"
    m_init = re.search(r'__version__\s*=\s*"([0-9.]+)"', init_file.read_text(encoding="utf-8"))
    if not m_init:
        return False, "Could not extract __version__ from src/dhcpt/__init__.py"
    init_ver = m_init.group(1)

    if pkg_ver != init_ver:
        return False, f"Version mismatch: pyproject.toml ({pkg_ver}) != src/dhcpt/__init__.py ({init_ver})"

    if man_file.is_file():
        m_man = re.search(r"%\s*DHCPT\(1\)\s*dhcpt\s+([0-9.]+)", man_file.read_text(encoding="utf-8"))
        if not m_man:
            return False, "Could not extract version from man/dhcpt.1.md header"
        man_ver = m_man.group(1)

        def parse_ver(v: str) -> tuple[int, ...]:
            return tuple(int(x) for x in v.split(".") if x.isdigit())

        parsed_pkg = parse_ver(pkg_ver)
        parsed_man = parse_ver(man_ver)

        if parsed_man < parsed_pkg:
            return False, (
                f"Manpage version ({man_ver}) in man/dhcpt.1.md is older than package version "
                f"({pkg_ver}) in pyproject.toml! Update man/dhcpt.1.md and run 'make man'."
            )
        elif parsed_man > parsed_pkg:
            return True, (
                f"WARNING: Manpage version ({man_ver}) is newer than pyproject.toml version ({pkg_ver}). "
                "Ensure pyproject.toml and src/dhcpt/__init__.py are updated before cutting a release."
            )

    return True, f"All component versions consistent ({pkg_ver})."


def test_repo_version_consistency() -> None:
    """Test version consistency across the actual repository files."""
    ok, msg = validate_version_consistency()
    assert ok is True
    assert "consistent" in msg or "WARNING" in msg


def test_version_consistency_scenarios(tmp_path: Path) -> None:
    """Test all version comparison edge cases and threshold behaviors."""
    # 1. Matching versions
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.2.0"\n', encoding="utf-8")
    src_pkg = tmp_path / "src" / "dhcpt"
    src_pkg.mkdir(parents=True)
    (src_pkg / "__init__.py").write_text('__version__ = "0.2.0"\n', encoding="utf-8")
    man_dir = tmp_path / "man"
    man_dir.mkdir(parents=True)
    (man_dir / "dhcpt.1.md").write_text("% DHCPT(1) dhcpt 0.2.0 | User Commands\n", encoding="utf-8")

    ok, msg = validate_version_consistency(tmp_path)
    assert ok is True
    assert "0.2.0" in msg

    # 2. Package version != init version -> failure
    (src_pkg / "__init__.py").write_text('__version__ = "0.1.9"\n', encoding="utf-8")
    ok, msg = validate_version_consistency(tmp_path)
    assert ok is False
    assert "Version mismatch" in msg

    # Restore matching init
    (src_pkg / "__init__.py").write_text('__version__ = "0.2.0"\n', encoding="utf-8")

    # 3. Manpage version older than package version -> failure (abort)
    (man_dir / "dhcpt.1.md").write_text("% DHCPT(1) dhcpt 0.1.1 | User Commands\n", encoding="utf-8")
    ok, msg = validate_version_consistency(tmp_path)
    assert ok is False
    assert "older than package version" in msg

    # 4. Manpage version newer than package version -> warning (returns True, warning msg)
    (man_dir / "dhcpt.1.md").write_text("% DHCPT(1) dhcpt 0.3.0 | User Commands\n", encoding="utf-8")
    ok, msg = validate_version_consistency(tmp_path)
    assert ok is True
    assert msg.startswith("WARNING")


def test_cli_standalone_version() -> None:
    """Verify that running src/dhcpt/cli.py --version directly matches pyproject.toml."""
    import subprocess

    root_dir = Path(__file__).resolve().parent.parent
    cli_py = root_dir / "src" / "dhcpt" / "cli.py"
    pyproject_file = root_dir / "pyproject.toml"

    assert cli_py.is_file(), f"Missing {cli_py}"
    assert pyproject_file.is_file(), f"Missing {pyproject_file}"

    m = re.search(r'version\s*=\s*"([0-9.]+)"', pyproject_file.read_text(encoding="utf-8"))
    assert m is not None, "Could not extract version from pyproject.toml"
    expected_ver = m.group(1)

    res = subprocess.run(
        [sys.executable, str(cli_py), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert f"dhcpt {expected_ver}" in res.stdout.strip()


if __name__ == "__main__":
    is_ok, message = validate_version_consistency()
    if message.startswith("WARNING"):
        print(f"[WARNING] {message}")
        sys.exit(0)
    elif not is_ok:
        print(f"[ERROR] {message}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"[OK] {message}")
        sys.exit(0)
