"""Check compiled opcode parsing, cache safety, and bounded temporary allocations."""

import importlib.machinery
import json
import os
import subprocess
import sys

import pytest
from web3 import Web3
from web3.providers.base import BaseProvider

from brownie._c_constants import HexBytes
from brownie.network.middlewares import caching


@pytest.fixture(autouse=True)
def compiled_parser():
    assert any(
        caching.__file__.endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES
    )


@pytest.mark.parametrize("width", range(1, 33))
def test_push_payload_is_data(width):
    opcode = bytes([0x5F + width])
    code = b"\x5f" + opcode + b"\xff" * width + b"\x01\xf4"
    assert caching._strip_push_data(code) == b"\x5f" + opcode + b"\x01\xf4"


@pytest.mark.parametrize(
    "code,expected",
    [
        (b"", b""),
        (b"\x5f\x00\x5b", b"\x5f\x00\x5b"),
        (b"\x7f\xff\xf4", b"\x7f"),
        (b"\x60", b"\x60"),
    ],
)
def test_empty_ordinary_and_truncated_instructions(code, expected):
    assert caching._strip_push_data(code) == expected


@pytest.mark.parametrize(
    "code,expected",
    [
        (b"", False),
        (b"\xff", False),
        (b"\xf4", False),
        (b"\x61\xff\xf4\x00", True),
        (b"\x60\x00\x5a\xf4", False),
    ],
)
def test_cache_safety_uses_opcodes(code, expected):
    assert caching.is_cacheable_bytecode(Web3(), HexBytes(code)) is expected


class CodeProvider(BaseProvider):
    def __init__(self, code):
        super().__init__()
        self.code = code
        self.calls = []

    def make_request(self, method, params):
        self.calls.append((method, params))
        assert method == "eth_getCode"
        return {"jsonrpc": "2.0", "id": 1, "result": self.code}


@pytest.mark.parametrize("target_code,expected", [("0x00", True), ("0xff", False)])
def test_fixed_delegate_target_keeps_cache_safety(target_code, expected):
    target = "0x1111111111111111111111111111111111111111"
    provider = CodeProvider(target_code)
    code = HexBytes(b"\x73" + bytes.fromhex(target[2:]) + b"\x5a\xf4")
    assert caching.is_cacheable_bytecode(Web3(provider), code) is expected
    assert provider.calls == [("eth_getCode", [target, "latest"])]


def test_repeated_compiled_parsing_releases_temporary_bytes(tmp_path):
    code = """
import gc, importlib.machinery, json, tracemalloc
from brownie.network.middlewares import caching
assert any(caching.__file__.endswith(s) for s in importlib.machinery.EXTENSION_SUFFIXES)
bytecode = (b'\\x7f' + b'\\xff' * 32 + b'\\x01') * 64
expected = b'\\x7f\\x01' * 64
tracemalloc.start()
before = tracemalloc.get_traced_memory()[0]
for _ in range(100):
    assert caching._strip_push_data(bytecode) == expected
gc.collect()
after, peak = tracemalloc.get_traced_memory()
print(json.dumps({'retained': after - before, 'peak': peak}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    measured = json.loads(result.stdout)
    # The returned 128 bytes have no owner here. Leave room for interpreter
    # bookkeeping, but reject the compiled parser's growing byte-string leak.
    assert measured["retained"] < 64 * 1024, measured
