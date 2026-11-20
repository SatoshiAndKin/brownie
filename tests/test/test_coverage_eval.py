from copy import deepcopy

import pytest

from brownie.test import coverage, output


def test_merge_transaction_path_sets_preserves_inputs():
    transactions = {
        "first": {"Example": {"0": [{1}, {2}, set()]}},
        "second": {"Example": {"0": [{3}, set(), {4}], "1": [{5}, set(), set()]}},
    }
    original = deepcopy(transactions)

    merged = coverage.get_merged_coverage_eval(transactions)

    assert merged == {"Example": {"0": [{1, 3}, {2}, {4}], "1": [{5}, set(), set()]}}
    assert transactions == original


def test_split_transaction_path_sets():
    coverage_map = {
        "statements": {"0": {"Example.run": {1: (0, 1), 2: (1, 2)}}},
        "branches": {"0": {"Example.run": {3: (2, 3, False), 4: (3, 4, True)}}},
    }

    assert output._split([{1}, {3}, {4}], coverage_map, "0") == {"Example.run": ([1], [3], [4])}


@pytest.mark.parametrize("jump, expected", [(True, "yellow"), (False, "orange")])
def test_branch_color_accepts_boolean_jump(jump, expected):
    assert output._branch_color(4, {"0": [set(), set(), {4}]}, "0", jump) == expected
