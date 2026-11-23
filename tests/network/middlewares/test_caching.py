#!/usr/bin/python3

import threading

import pytest

from brownie._config import CONFIG
from brownie.network.middlewares.caching import RequestCachingMiddleware


@pytest.fixture
def middleware(accounts, web3, monkeypatch):
    monkeypatch.setitem(CONFIG.active_network, "chainid", web3.eth.chain_id)
    instance = RequestCachingMiddleware(web3)
    instance.uninstall()
    monkeypatch.setattr(web3, "isConnected", lambda: False)
    instance.is_killed = False
    instance.event.clear()
    instance._stop_event.clear()
    instance.block_cache.clear()
    yield instance
    instance.uninstall()
    instance.cur.close()


def test_uninstall_stops_waiting_filter_thread(middleware):
    middleware.block_cache["block"] = {}

    started = threading.Event()

    def wait_for_event():
        started.set()
        middleware.event.wait(5)

    middleware.loop_thread = threading.Thread(target=wait_for_event)
    middleware.loop_thread.start()
    assert started.wait(1)
    assert middleware.loop_thread.is_alive()

    middleware.uninstall()

    assert middleware.is_killed is True
    assert middleware._stop_event.is_set()
    assert middleware.event.is_set()
    assert middleware.block_cache == {}
    assert not middleware.loop_thread.is_alive()


def test_uninstall_does_not_join_current_thread(middleware):
    middleware.loop_thread = threading.current_thread()

    middleware.uninstall()

    assert middleware.is_killed is True
    assert middleware._stop_event.is_set()
    assert middleware.event.is_set()


def test_loop_exception_handler_releases_startup_waiters(middleware, web3, monkeypatch):
    def raise_before_initialization(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(web3.eth, "get_block", raise_before_initialization)

    middleware.loop_exception_handler()

    assert middleware.is_killed is True
    assert middleware.event.is_set()
