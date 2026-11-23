"""Public input contracts must also work in the installed native wheel."""

from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path

import pytest

from brownie import _config, project
from brownie.convert import datatypes
from brownie.test import coverage


@pytest.fixture(autouse=True)
def installed_native_modules():
    for module in (_config, project.main, datatypes, coverage):
        assert module.__file__.endswith(tuple(EXTENSION_SUFFIXES))


def test_project_new_accepts_path(tmp_path):
    destination = tmp_path / "project"
    assert project.new(destination) == str(destination)
    assert (destination / "contracts").is_dir()


@pytest.mark.parametrize(
    "left,right",
    [(88, 88), (datatypes.Wei(10**19), 10**19), ("1 ether", 10**18), ("plain", "plain")],
)
def test_return_value_compares_mixed_values(left, right):
    assert datatypes.ReturnValue((left,)) == [right]


def test_coverage_merges_list_backed_paths():
    first = {"Token": {"0": [{1}, {2}, set()]}}
    second = {"Token": {"0": [{3}, set(), {4}]}}
    assert coverage.get_merged_coverage_eval({"a": first, "b": second}) == {
        "Token": {"0": [{1, 3}, {2}, {4}]}
    }
    assert first == {"Token": {"0": [{1}, {2}, set()]}}
    assert second == {"Token": {"0": [{3}, set(), {4}]}}


def test_data_folder_override_reaches_native_callers(monkeypatch, tmp_path):
    monkeypatch.setattr(_config, "DATA_FOLDER", Path(tmp_path))
    assert _config._get_data_folder() == tmp_path
