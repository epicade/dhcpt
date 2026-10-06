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
"""Validate software license compliance and legal integrity.

Verifies that:
1. Repository license file (LICENSE) exists and contains GNU General Public License v2 text.
2. Package metadata in pyproject.toml explicitly declares GPL-2.0-or-later.
3. Runtime dependencies in pyproject.toml (project.dependencies) are legally compatible
   with GPLv2 copyleft terms, ensuring no Apache-2.0 or proprietary code is introduced.
"""

from __future__ import annotations

import email.message
import importlib.metadata
import re
from pathlib import Path

import pytest


def get_project_root() -> Path:
    """Locate repository root directory."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").is_file():
            return current
        current = current.parent
    raise FileNotFoundError("Could not locate repository root directory.")


def test_license_file_present_and_valid() -> None:
    """Verify that LICENSE exists in repository root and contains GPLv2 text."""
    root = get_project_root()
    license_file = root / "LICENSE"

    assert license_file.is_file(), f"Missing LICENSE file at {license_file}"
    content = license_file.read_text(encoding="utf-8")

    assert "GNU GENERAL PUBLIC LICENSE" in content
    assert "Version 2, June 1991" in content
    assert "TERMS AND CONDITIONS FOR COPYING, DISTRIBUTION AND MODIFICATION" in content


def test_pyproject_declares_gpl2_or_later() -> None:
    """Verify pyproject.toml license field and PyPI classifiers declare GPL-2.0-or-later."""
    root = get_project_root()
    pyproject_file = root / "pyproject.toml"

    assert pyproject_file.is_file(), f"Missing pyproject.toml at {pyproject_file}"
    content = pyproject_file.read_text(encoding="utf-8")

    # Check license declaration (string format per PEP 639 / Hatchling)
    assert re.search(r'license\s*=\s*"GPL-2\.0-or-later"', content) is not None, (
        'pyproject.toml must declare: license = "GPL-2.0-or-later"'
    )

    # Check PyPI classifier
    assert "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)" in content, (
        "pyproject.toml classifiers must declare GPLv2+ OSI classifier"
    )

    # Check sdist includes LICENSE
    assert '"/LICENSE"' in content, "pyproject.toml [tool.hatch.build.targets.sdist] must include '/LICENSE'"


def check_dependency_license_compatibility(pkg_name: str, meta: importlib.metadata.PackageMetadata) -> None:
    """Validate that a single package metadata does not declare an incompatible license."""
    incompatible_patterns = [
        re.compile(r"\bapache\b", re.IGNORECASE),
        re.compile(r"\bproprietary\b", re.IGNORECASE),
        re.compile(r"\bcommercial\b", re.IGNORECASE),
    ]

    license_name = meta.get("License") or ""
    license_expr = meta.get("License-Expression") or ""
    classifiers = [c for c in meta.get_all("Classifier") or [] if "License" in c]

    all_license_texts = [license_name, license_expr] + classifiers

    for text in all_license_texts:
        for pattern in incompatible_patterns:
            if pattern.search(text):
                raise AssertionError(
                    f"Incompatible license detected for runtime dependency '{pkg_name}': '{text}'. "
                    "Apache-2.0 or proprietary code is legally incompatible with GPLv2 copyleft terms!"
                )


def test_runtime_dependencies_gpl_compatibility() -> None:
    """Ensure all runtime dependencies are compatible with GPLv2 copyleft terms.

    Flags Apache-2.0 or proprietary libraries, which are legally incompatible with Scapy's GPLv2 license.
    """
    root = get_project_root()
    pyproject_file = root / "pyproject.toml"
    content = pyproject_file.read_text(encoding="utf-8")

    # Extract project.dependencies block
    m = re.search(r"dependencies\s*=\s*\[(.*?)\]", content, re.DOTALL)
    assert m is not None, "Could not locate project.dependencies in pyproject.toml"

    raw_deps = m.group(1)
    dep_names: list[str] = []
    for line in raw_deps.splitlines():
        line = line.strip().strip(",").strip('"').strip("'")
        if not line or line.startswith("#"):
            continue
        # Extract base package name before version specifiers (e.g. "scapy>=2.5.0" -> "scapy")
        pkg_name = re.split(r"[><=~!]", line)[0].strip()
        if pkg_name:
            dep_names.append(pkg_name)

    assert len(dep_names) > 0, "No runtime dependencies found in pyproject.toml"

    for pkg in dep_names:
        try:
            meta = importlib.metadata.metadata(pkg)
        except importlib.metadata.PackageNotFoundError:
            # Package might not be installed in current test runner
            continue

        check_dependency_license_compatibility(pkg, meta)


def test_incompatible_license_detection_fails() -> None:
    """Verify that an Apache-2.0 runtime dependency triggers an immediate AssertionError."""
    fake_meta = email.message.EmailMessage()
    fake_meta["Name"] = "fake-apache-lib"
    fake_meta["License"] = "Apache-2.0"

    with pytest.raises(AssertionError, match="Incompatible license detected.*Apache-2.0"):
        check_dependency_license_compatibility("fake-apache-lib", fake_meta)
