"""Bytecode scans release their intermediate buffers in native and Python builds."""

import tracemalloc

import pytest

from brownie.network.middlewares.caching import _strip_push_data


@pytest.mark.parametrize("push_size", range(1, 33))
def test_push_data_is_removed_without_removing_opcodes(push_size):
    opcode = bytes([0x5F + push_size])
    assert _strip_push_data(opcode + b"\xff" * push_size + b"\x00\xff") == opcode + b"\x00\xff"
    assert _strip_push_data(opcode + b"\xff" * (push_size - 1)) == opcode


def test_repeated_scans_release_intermediate_byte_buffers():
    bytecode = (b"\x7f" + b"\xff" * 32 + b"\x00") * 512
    expected = b"\x7f\x00" * 512
    already_tracing = tracemalloc.is_tracing()
    if not already_tracing:
        tracemalloc.start()
    try:
        before = tracemalloc.get_traced_memory()[0]
        for _ in range(16):
            assert _strip_push_data(bytecode) == expected
        retained = tracemalloc.get_traced_memory()[0] - before
        # A compiler ownership defect retained 4,464,096 bytes in these scans.
        assert retained < 64 * 1024
    finally:
        if not already_tracing:
            tracemalloc.stop()
