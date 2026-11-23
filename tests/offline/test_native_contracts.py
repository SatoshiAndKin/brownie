"""Public input contracts must also work in the installed native wheel."""

from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path

import pytest

from brownie import _config, project
from brownie.convert import datatypes, to_address
from brownie.network.account import PublicKeyAccount
from brownie.network.state import TxHistory
from brownie.test import coverage, output


@pytest.fixture(autouse=True)
def installed_native_modules():
    for module in (_config, project.main, datatypes, coverage, output):
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


def test_vyper_current_source_map_format():
    source = """# @version 0.4.3
@external
@view
def value() -> uint256:
    return 31337
"""
    compiled = project.compiler.compile_and_format(
        {"Vyper_contract.vy": source}, vyper_version="0.4.3"
    )
    assert compiled["Vyper_contract"]["pcMap"]
    assert compiled["Vyper_contract"]["allSourcePaths"] == {"0": "Vyper_contract.vy"}


def test_account_objects_are_valid_address_inputs():
    account = PublicKeyAccount("0x0000000000000000000000000000000000000001")
    assert to_address(account) == account.address
    history = TxHistory()
    assert history.from_sender(account) == []
    assert history.to_receiver(account) == []
    assert history.of_address(account) == []


@pytest.mark.parametrize("setting", ["Token", ["Token"]])
def test_report_exclusions_accept_string_or_list(setting):
    assert output._load_report_exclude_data(
        {"exclude_paths": None, "exclude_contracts": setting}
    ) == ([], ["Token"])
