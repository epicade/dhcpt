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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""Test suite verifying syntax validity of all repository YAML configuration and workflow files."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def get_project_root() -> Path:
    """Locate repository root directory."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").is_file():
            return current
        current = current.parent
    raise FileNotFoundError("Could not locate repository root directory.")


def get_all_yaml_files() -> list[Path]:
    """Find all YAML files across the repository."""
    root = get_project_root()
    yaml_files: list[Path] = []
    for pattern in ("*.yml", "*.yaml", ".github/**/*.yml", ".github/**/*.yaml"):
        yaml_files.extend(root.glob(pattern))
    return sorted(set(yaml_files))


def test_yaml_files_exist() -> None:
    """Ensure at least one YAML workflow file is discovered."""
    files = get_all_yaml_files()
    assert len(files) > 0, "No YAML files found in repository"


@pytest.mark.parametrize("yaml_path", get_all_yaml_files(), ids=lambda p: str(p.name))
def test_yaml_syntax_validity(yaml_path: Path) -> None:
    """Parse each YAML file using yaml.safe_load to guarantee valid syntax."""
    assert yaml_path.is_file(), f"YAML file missing: {yaml_path}"
    content = yaml_path.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    assert data is not None, f"YAML file {yaml_path} produced empty or None document"
