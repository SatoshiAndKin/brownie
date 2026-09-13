"""Explorer transport regressions; no node or explorer credentials required."""

from types import SimpleNamespace

import pytest
import requests

from brownie.network import contract

ADDRESS = "0x0000000000000000000000000000000000000001"
RESULT = {"status": "1", "result": [{"ABI": "[]", "SourceCode": "contract C {}"}]}


@pytest.fixture
def explorer(monkeypatch):
    monkeypatch.setattr(
        contract,
        "web3",
        SimpleNamespace(
            eth=SimpleNamespace(get_code=lambda address: b"\x60\x00"), chain_id=1
        ),
    )
    monkeypatch.setattr(contract, "_unverified_addresses", set())
    monkeypatch.delenv("ETHERSCAN_TOKEN", raising=False)

    def install(*outcomes):
        calls = []
        replies = iter(outcomes)

        def get(url, **kwargs):
            calls.append((url, kwargs))
            assert kwargs["timeout"] == (10, 30)
            reply = next(replies)
            if isinstance(reply, Exception):
                raise reply
            status, payload = reply if isinstance(reply, tuple) else (reply, RESULT)
            return SimpleNamespace(
                status_code=status,
                text="response",
                json=lambda: payload,
                close=lambda: None,
            )

        monkeypatch.setattr(contract.requests, "get", get)
        return calls

    return install


def test_unverified_source_has_the_same_typed_error_on_first_and_cached_reads(explorer):
    calls = explorer(
        (
            200,
            {
                "status": "0",
                "message": "NOTOK",
                "result": "Contract source code not verified",
            },
        )
    )
    with pytest.raises(ValueError) as first:
        contract._fetch_from_explorer(ADDRESS, "getabi", True)
    assert type(first.value).__name__ == "ContractNotVerified"
    assert str(first.value) == f"Source for {ADDRESS} has not been verified"
    contract._unverified_addresses.add(ADDRESS)
    with pytest.raises(type(first.value), match=str(first.value)):
        contract._fetch_from_explorer(ADDRESS, "getsourcecode", True)
    assert len(calls) == 1


def test_api_failure_is_infrastructure_not_unverified_source(explorer):
    calls = explorer(
        (200, {"status": "0", "message": "NOTOK", "result": "Invalid API Key"})
    )
    with pytest.raises(ConnectionError, match="Invalid API Key"):
        contract._fetch_from_explorer(ADDRESS, "getabi", True)
    assert ADDRESS not in contract._unverified_addresses
    assert len(calls) == 1


@pytest.mark.parametrize(
    "failure", [requests.ConnectTimeout, requests.ReadTimeout, requests.ConnectionError]
)
def test_transient_request_recovers_once(explorer, failure):
    calls = explorer(failure("stalled"), 200)
    assert contract._fetch_from_explorer(ADDRESS, "getsourcecode", True) == RESULT
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert calls[0][1]["params"] == {
        "module": "contract",
        "action": "getsourcecode",
        "address": ADDRESS,
        "chainid": 1,
    }


@pytest.mark.parametrize(
    "failure", [requests.ConnectTimeout, requests.ReadTimeout, requests.ConnectionError]
)
def test_retry_exhaustion_is_infrastructure_error(explorer, failure):
    calls = explorer(failure("stalled"), failure("still stalled"))
    with pytest.raises(
        ConnectionError, match="Etherscan getsourcecode.*after 2 attempts"
    ) as error:
        contract._fetch_from_explorer(ADDRESS, "getsourcecode", True)
    assert isinstance(error.value.__cause__, failure)
    assert len(calls) == 2
    assert ADDRESS not in contract._unverified_addresses


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_transient_http_recovers_once(explorer, status):
    calls = explorer(status, 200)
    assert contract._fetch_from_explorer(ADDRESS, "getabi", True) == RESULT
    assert len(calls) == 2


@pytest.mark.parametrize("status,attempts", [(400, 1), (401, 1), (404, 1), (503, 2)])
def test_http_failure_is_bounded(explorer, status, attempts):
    calls = explorer(status, status)
    with pytest.raises(
        ConnectionError, match=f"HTTP {status}.*after {attempts} attempt"
    ):
        contract._fetch_from_explorer(ADDRESS, "getsourcecode", True)
    assert len(calls) == attempts


def test_success_uses_one_request(explorer):
    calls = explorer(200)
    assert contract._fetch_from_explorer(ADDRESS, "getsourcecode", True) == RESULT
    assert len(calls) == 1


def test_certificate_failure_is_not_retried(explorer):
    calls = explorer(requests.exceptions.SSLError("certificate failed"))
    with pytest.raises(ConnectionError, match="after 1 attempt") as error:
        contract._fetch_from_explorer(ADDRESS, "getsourcecode", True)
    assert isinstance(error.value.__cause__, requests.exceptions.SSLError)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "protocol,recover", [("http", False), ("http", True), ("https", False)]
)
def test_real_stalled_connection_or_read_has_a_finite_deadline(
    monkeypatch, protocol, recover
):
    import socketserver
    import threading

    requests_seen = []
    release = threading.Event()

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.recv(4096)
            requests_seen.append(True)
            if recover and len(requests_seen) == 2:
                body = b'{"status":"1","result":[]}'
                self.request.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Length: "
                    + str(len(body)).encode()
                    + b"\r\n\r\n"
                    + body
                )
            else:
                release.wait(70)

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True

    monkeypatch.setattr(
        contract,
        "web3",
        SimpleNamespace(
            eth=SimpleNamespace(get_code=lambda address: b"\x60\x00"), chain_id=1
        ),
    )
    monkeypatch.setattr(contract, "_unverified_addresses", set())
    monkeypatch.delenv("ETHERSCAN_TOKEN", raising=False)
    get = requests.get
    with Server(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def local_get(url, **kwargs):
            assert kwargs["timeout"] == (10, 30)
            return get(f"{protocol}://127.0.0.1:{server.server_address[1]}", **kwargs)

        monkeypatch.setattr(contract.requests, "get", local_get)
        try:
            if recover:
                assert contract._fetch_from_explorer(
                    ADDRESS, "getsourcecode", True
                ) == {
                    "status": "1",
                    "result": [],
                }
            else:
                with pytest.raises(ConnectionError, match="after 2 attempts") as error:
                    contract._fetch_from_explorer(ADDRESS, "getsourcecode", True)
                assert isinstance(error.value.__cause__, requests.Timeout)
            assert requests_seen == [True, True]
        finally:
            release.set()
            server.shutdown()
            thread.join()
