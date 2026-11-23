"""This script is the entrypoint for brownie's test suite.

In order to support eth-typing v5, we must patch eth-typing for testing.
pytest-ethereum is an unmaintained yet critical dependency of our testing flow
and requires a NewType, `ContractName` which was removed in eth-typing v5.

We must be sure it is patched before pytest starts up and attempts
to load any plugins.
"""

import sys
from pathlib import Path
from typing import Any, NewType

import eth_typing
import pytest

# Patch eth_typing (if the currently installed version is missing ContractName)
if not hasattr(eth_typing, "ContractName"):
    eth_typing.ContractName = NewType("ContractName", str)
    eth_typing.Manifest = NewType("Manifest", dict[str, Any])

# Load Brownie from the installed wheel before pytest imports checkout fixtures.
source_root = Path(__file__).resolve().parent
sys.path[:] = [entry for entry in sys.path if Path(entry or ".").resolve() != source_root]

import brownie  # noqa: E402

if Path(brownie.__file__).resolve().is_relative_to(source_root / "brownie"):
    raise RuntimeError("Tests must use the installed Brownie wheel")

# Now run pytest, forwarding all CLI arguments.
sys.exit(pytest.main(sys.argv[1:]))
